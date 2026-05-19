"""Aka-dora (red five) parsing + counting + han propagation."""

from __future__ import annotations

import pytest

from backend.app.mahjong.analyzer import analyze_game
from backend.app.mahjong.game import GameState, Meld, total_user_aka, visible_aka_in_player
from backend.app.mahjong.shanten import calculate_shanten, clear_cache
from backend.app.mahjong.tiles import (
    AKA_TILE_IDS,
    is_aka_code,
    parse_hand,
    tile_id_from_code,
)


def _id(code: str) -> int:
    return tile_id_from_code(code)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


# ---------- parsing ------------------------------------------------------


def test_aka_codes_normalize_to_regular_five():
    assert tile_id_from_code("0m") == 4
    assert tile_id_from_code("0p") == 13
    assert tile_id_from_code("0s") == 22
    assert is_aka_code("0m") and is_aka_code("0p") and is_aka_code("0s")
    assert not is_aka_code("5m")
    assert not is_aka_code("0z")


def test_parse_hand_with_aka_codes():
    ids = parse_hand("0m5m0p")
    # All three normalize to their regular ids.
    assert ids == [4, 4, 13]


def test_aka_tile_id_constants():
    assert AKA_TILE_IDS == (4, 13, 22)


# ---------- shanten / chi / pon / kan unaffected by red identity ----------


def test_red_five_used_in_chi():
    # Hand 4m + 5m (red) + 6m -> a chi/sequence including the red 5.
    state = GameState.from_hand(
        "4m5m6m4p5p6p7s8s9s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.aka_in_hand = 1  # mark the 5m as red
    sh = calculate_shanten(state.hand_counts())
    assert sh == 0  # tenpai shanpon


def test_red_five_used_in_pon():
    # Open pon of 5p where 1 of the 3 tiles is the red 5p.
    state = GameState.from_hand(
        "4m5m6m1z1z7s8s9s2z2z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [
        Meld(type="pon", tiles=[13, 13, 13], called_from=1, aka_count=1)
    ]
    res = analyze_game(state)
    # Engine still computes shanten correctly with the meld present.
    assert res["shanten"] in (0, 1)
    # Aka info propagates to value hints.
    assert res["value_hints"]["aka_dora_in_hand"] == 1


def test_red_five_used_in_open_kan():
    state = GameState.from_hand(
        "4m6m1z1z7s8s9s2z2z3z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [
        Meld(type="kan", tiles=[13, 13, 13, 13], called_from=2, aka_count=1)
    ]
    res = analyze_game(state)
    assert "shanten" in res
    assert res["value_hints"]["aka_dora_in_hand"] == 1


# ---------- aka counts both ways ----------------------------------------


def test_total_user_aka_sums_hand_and_melds():
    state = GameState.from_hand("123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z")
    state.aka_in_hand = 1
    state.user.melds = [Meld(type="pon", tiles=[22, 22, 22], called_from=1, aka_count=1)]
    assert total_user_aka(state) == 2


def test_visible_aka_in_opp_player():
    p_state = type(
        "P", (), {"melds": [Meld(type="pon", tiles=[4, 4, 4], called_from=2, aka_count=1)]}
    )()
    assert visible_aka_in_player(p_state) == 1


def test_aka_counts_as_dora_in_value_hints():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.aka_in_hand = 2
    res = analyze_game(state)
    assert res["value_hints"]["aka_dora_in_hand"] == 2


def test_aka_added_to_user_han_estimate():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.aka_in_hand = 2
    res = analyze_game(state)
    user_han = res["han_estimates"][0]
    assert user_han["seat"] == 0
    assert user_han["breakdown"].get("aka_dora") == 2


# ---------- aka-aware tile-count rules ----------------------------------


def test_red_five_counts_as_both_red_and_normal_dora_when_indicator_makes_5_dora():
    # Indicator 4m -> 5m is dora. Hand contains a red 5m (aka).
    # The red 5m should count as BOTH red dora (+1) AND normal dora (+1).
    state = GameState.from_hand(
        "1m2m3m5m6p7p8p9p7s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],
    )
    state.aka_in_hand = 1  # the 5m in hand is the red copy
    res = analyze_game(state)
    # value_hints reports them as separate buckets (correct for display).
    assert res["value_hints"]["dora_in_hand"] == 1      # the 5m matches the dora target
    assert res["value_hints"]["aka_dora_in_hand"] == 1  # the red identity
    # The user han breakdown sums both.
    user_han = res["han_estimates"][0]
    assert user_han["breakdown"].get("dora", 0) == 1
    assert user_han["breakdown"].get("aka_dora", 0) == 1
    assert user_han["han"] >= 2


def test_red_5p_used_in_chi_pattern_via_normal_5p():
    # Chi 4p-5p-6p where the 5p is the red copy. Closed hand has 10 tiles
    # (= 13 - 3 since the chi consumes one slot worth of closed tiles).
    state = GameState.from_hand(
        "1m2m3m4m5m6m7m8m9m7z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [
        Meld(type="chi", tiles=[12, 13, 14], called_from=3, aka_count=1)
    ]
    res = analyze_game(state)
    # Engine accepts the meld and treats it as a completed sequence.
    assert "shanten" in res
    # Aka info propagates.
    assert res["value_hints"]["aka_dora_in_hand"] == 1


def test_red_5_normalizes_for_shanten_max_4_combined():
    # 3 normal 5m + 1 red 5m (combined 4) is valid; shanten still computable.
    state = GameState.from_hand(
        "5m5m5m1m2m3m4p5p6p7s8s9s7z", round_wind="1z", seat_wind="1z"
    )
    state.aka_in_hand = 1  # one of the 5m is red — same base id, just flagged
    # Engine treats all four "5m" tiles identically for shanten.
    sh = calculate_shanten(state.hand_counts())
    assert isinstance(sh, int)
    res = analyze_game(state)
    # Aka still surfaces in value hints despite normalisation.
    assert res["value_hints"]["aka_dora_in_hand"] == 1
