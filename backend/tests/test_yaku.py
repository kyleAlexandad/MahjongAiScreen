"""Yaku-direction detection tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.game import GameState, Meld
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code
from backend.app.mahjong.yaku import analyze_yaku_directions


def _id(code: str) -> int:
    return tile_id_from_code(code)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _direction(result: dict, name: str) -> dict | None:
    for d in result["directions"]:
        if d["name"] == name:
            return d
    return None


# ---- Tanyao --------------------------------------------------------------


def test_tanyao_high_confidence_when_no_terminals_or_honors():
    # All simples (2-8 only). 13 tiles.
    state = GameState.from_hand(
        "234m345m456p678p23s", round_wind="1z", seat_wind="1z"
    )
    assert sum(state.hand_counts()) == 14
    # Drop a tile so we're between turns.
    state.hand.pop()
    res = analyze_yaku_directions(state)
    d = _direction(res, "tanyao")
    assert d is not None
    assert d["confidence"] >= 80


def test_tanyao_killed_by_terminal_meld():
    state = GameState.from_hand(
        "234m345m456p23s", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [Meld(type="pon", tiles=[_id("1m"), _id("1m"), _id("1m")], called_from=1)]
    res = analyze_yaku_directions(state)
    assert _direction(res, "tanyao") is None


# ---- Yakuhai -------------------------------------------------------------


def test_yakuhai_pair_of_dragons():
    # Pair of Haku (5z, dragon)
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z2m4m", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    yh = next((d for d in res["directions"] if d["name"].startswith("yakuhai_")), None)
    assert yh is not None
    assert yh["confidence"] >= 70
    assert _id("5z") in yh["keep_tile_ids"]
    # tile_reasons should mark 5z with 'yakuhai'
    assert "yakuhai" in res["tile_reasons"][str(_id("5z"))]


def test_yakuhai_pair_of_seat_wind():
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s2z2z2m3m", round_wind="1z", seat_wind="2z"
    )
    res = analyze_yaku_directions(state)
    yh = next((d for d in res["directions"] if d["name"].startswith("yakuhai_")), None)
    assert yh is not None
    assert _id("2z") in yh["keep_tile_ids"]


def test_no_yakuhai_for_off_wind_pair():
    # Pair of West, but round=East and seat=South -> not yakuhai for this player.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s3z3z2m3m", round_wind="1z", seat_wind="2z"
    )
    res = analyze_yaku_directions(state)
    yh = next((d for d in res["directions"] if d["name"].startswith("yakuhai_")), None)
    assert yh is None


# ---- Honitsu / Chinitsu -------------------------------------------------


def test_honitsu_high_confidence_with_one_suit_plus_honors():
    state = GameState.from_hand(
        "1m2m3m4m5m6m7m8m9m1z1z2z3z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    d = _direction(res, "honitsu")
    assert d is not None and d["confidence"] >= 80
    # Tiles in dominant suit + honors should be flagged 'keep_honitsu'
    assert "keep_honitsu" in res["tile_reasons"][str(_id("5m"))]


def test_chinitsu_when_one_suit_only():
    state = GameState.from_hand(
        "1m2m3m4m5m6m7m8m9m1m2m3m4m", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    d = _direction(res, "chinitsu")
    assert d is not None
    assert d["confidence"] >= 80
    # Honitsu confidence should also be high (chinitsu is a special case)
    assert _direction(res, "honitsu") is not None


def test_honitsu_killed_by_off_suit_meld():
    state = GameState.from_hand(
        "1m2m3m4m5m6m7m8m9m1z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [Meld(type="pon", tiles=[_id("5p"), _id("5p"), _id("5p")], called_from=1)]
    res = analyze_yaku_directions(state)
    assert _direction(res, "honitsu") is None


# ---- Toitoi -------------------------------------------------------------


def test_toitoi_with_many_pairs():
    # 13 tiles: 6 pairs + 1 single.
    state = GameState.from_hand(
        "11m22m33m44p55p66s7z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    d = _direction(res, "toitoi")
    assert d is not None
    assert d["confidence"] >= 50


def test_toitoi_killed_by_chi():
    # Closed (after 1 chi meld) = 13 - 3 = 10 tiles.
    state = GameState.from_hand(
        "11m22m33m44p55p", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [Meld(type="chi", tiles=[_id("3s"), _id("4s"), _id("5s")], called_from=3)]
    res = analyze_yaku_directions(state)
    assert _direction(res, "toitoi") is None


# ---- Chiitoitsu / Kokushi ------------------------------------------------


def test_chiitoitsu_direction_at_low_shanten():
    state = GameState.from_hand(
        "11m22m33m44p55p66p7z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    d = _direction(res, "chiitoitsu")
    assert d is not None and d["confidence"] >= 60


def test_kokushi_direction_at_low_shanten():
    state = GameState.from_hand(
        "19m19p19s1234567z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    d = _direction(res, "kokushi")
    assert d is not None and d["confidence"] >= 70


# ---- Dora ----------------------------------------------------------------


def test_dora_counted_in_hand():
    # dora indicator 4m -> dora tile = 5m
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5m5m5z5z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],
    )
    res = analyze_yaku_directions(state)
    assert res["value_hints"]["dora_in_hand"] == 2
    assert "dora" in res["tile_reasons"][str(_id("5m"))]


# ---- Smoke: tile_reasons key shape --------------------------------------


def test_tile_reasons_keys_are_serialisable():
    state = GameState.from_hand(
        "234m345m456p678p2s", round_wind="1z", seat_wind="1z"
    )
    res = analyze_yaku_directions(state)
    for k, v in res["tile_reasons"].items():
        assert isinstance(k, str) and k.isdigit()
        assert isinstance(v, list)
        for r in v:
            assert isinstance(r, str)
