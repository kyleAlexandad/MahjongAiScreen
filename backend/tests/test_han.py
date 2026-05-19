"""Han-estimate tests (user + opponent visible-only)."""

from __future__ import annotations

import pytest

from backend.app.mahjong.analyzer import analyze_game
from backend.app.mahjong.game import GameState, Meld
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code


def _id(code: str) -> int:
    return tile_id_from_code(code)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _opp_han(res, seat):
    return next(h for h in res["han_estimates"] if h["seat"] == seat)


# ---- user --------------------------------------------------------------


def test_user_han_riichi_plus_one():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.user.riichi = True
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["breakdown"].get("riichi") == 1
    assert user["han"] >= 1


def test_user_han_yakuhai_triplet_counted():
    # 1z = East = round wind = seat wind => double yakuhai when melded as triplet.
    state = GameState.from_hand(
        "123m456p789s1z1z1z2z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_game(state)
    user = res["han_estimates"][0]
    # Concealed triplet of double-wind counts as 2.
    assert user["breakdown"].get("yakuhai", 0) >= 2


def test_user_han_dora_added():
    # Dora indicator 4m -> 5m is dora; user has two 5m.
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],
    )
    state.hand[3] = _id("5m")  # swap a 4p? simpler approach below
    # Rebuild with 5m explicitly:
    state = GameState.from_hand(
        "1m2m3m5m5m6p7p8p9s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],
    )
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["breakdown"].get("dora", 0) == 2


def test_user_han_aka_added():
    state = GameState.from_hand(
        "1m2m3m5m6p7p8p9p7s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.aka_in_hand = 1
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["breakdown"].get("aka_dora", 0) == 1


# ---- opponent (visible-only) -------------------------------------------


def test_opp_han_riichi_only():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.opponents[0].riichi = True
    state.opponents[0].riichi_discard_index = 0
    res = analyze_game(state)
    opp = _opp_han(res, 1)
    assert opp["breakdown"].get("riichi") == 1
    assert opp["han"] == 1
    assert opp["estimate"] is True


def test_opp_visible_yakuhai_pon_dragon():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.opponents[1].melds = [
        Meld(type="pon", tiles=[_id("5z"), _id("5z"), _id("5z")], called_from=0)
    ]
    res = analyze_game(state)
    opp = _opp_han(res, 2)
    assert opp["breakdown"].get("visible_yakuhai") == 1


def test_opp_visible_seat_wind_pon():
    # Round = East. Opp at seat 2 (toimen). User is East (seat 0).
    # Toimen is West (winds order E,S,W,N counter-clockwise from user).
    # So toimen pon of 3z = West would BE their seat wind -> yakuhai.
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.opponents[1].melds = [
        Meld(type="pon", tiles=[_id("3z"), _id("3z"), _id("3z")], called_from=0)
    ]
    res = analyze_game(state)
    opp = _opp_han(res, 2)
    # 3z is the round-wind for nobody (round=1z=East), but it's toimen's
    # seat wind (since toimen sits West when user is East).
    assert opp["breakdown"].get("visible_yakuhai", 0) == 1


def test_opp_visible_dora_in_meld():
    # Dora indicator 1m -> dora is 2m. Opp has chi 1-2-3m (one 2m = 1 dora).
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("1m")],
    )
    state.opponents[0].melds = [
        Meld(type="chi", tiles=[_id("1m"), _id("2m"), _id("3m")], called_from=3)
    ]
    res = analyze_game(state)
    opp = _opp_han(res, 1)
    assert opp["breakdown"].get("visible_dora", 0) == 1


def test_opp_visible_aka_in_meld():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.opponents[2].melds = [
        Meld(type="pon", tiles=[_id("5p"), _id("5p"), _id("5p")], called_from=1, aka_count=1)
    ]
    res = analyze_game(state)
    opp = _opp_han(res, 3)
    assert opp["breakdown"].get("visible_aka", 0) == 1


# ---- shape: every analyse-game response contains 4 han estimates --------


def test_han_estimates_always_have_four_seats():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_game(state)
    assert len(res["han_estimates"]) == 4
    seats = sorted(h["seat"] for h in res["han_estimates"])
    assert seats == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# Yaku han vs Dora han split (Phase 2.10)
# ---------------------------------------------------------------------------


def test_user_yaku_han_excludes_dora():
    # Riichi (1 yaku han) + dora 2m * 2 (2 dora han).
    state = GameState.from_hand(
        "1m2m3m5m5m6p7p8p9p7s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],  # 5m is dora
    )
    state.user.riichi = True
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["yaku_han"] >= 1   # at least riichi
    assert user["dora_han"] == 2
    assert user["has_yaku"] is True
    assert user["han"] == user["yaku_han"] + user["dora_han"]


def test_user_dora_alone_marked_no_yaku():
    # 2 dora (no riichi, no yakuhai detected) -> dora_han > 0 but has_yaku False.
    state = GameState.from_hand(
        "1m2m3m5m5m6p7p8p9p7s9s2z2z3z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],  # 5m dora x2
    )
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["dora_han"] >= 2
    if user["yaku_han"] == 0:
        assert user["has_yaku"] is False
        # Notes should explicitly warn that dora alone is not a yaku.
        notes = " ".join(user["notes"]).lower()
        assert "dora alone is not a yaku" in notes


def test_user_aka_dora_counts_in_dora_han():
    state = GameState.from_hand(
        "1m2m3m5m6p7p8p9p7s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.aka_in_hand = 1
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["dora_han"] >= 1
    assert user["breakdown"].get("aka_dora", 0) == 1


def test_user_red_5_that_is_also_dora_counts_double():
    # Indicator 4m -> 5m dora. User has 5m which is the red five.
    state = GameState.from_hand(
        "1m2m3m5m6p7p8p9p7s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],
    )
    state.aka_in_hand = 1
    res = analyze_game(state)
    user = res["han_estimates"][0]
    assert user["breakdown"].get("dora", 0) == 1
    assert user["breakdown"].get("aka_dora", 0) == 1
    assert user["dora_han"] == 2


def test_opp_visible_yaku_and_dora_split():
    state = GameState.from_hand(
        "123m456p789s1z1z2z2z", round_wind="1z", seat_wind="1z",
        dora_indicators=[_id("4m")],
    )
    state.opponents[1].melds = [
        Meld(type="pon", tiles=[_id("5z"), _id("5z"), _id("5z")], called_from=0),
        Meld(type="chi", tiles=[_id("3m"), _id("4m"), _id("5m")], called_from=3),
    ]
    res = analyze_game(state)
    opp = _opp_han(res, 2)
    assert opp["yaku_han"] == 1   # haku triplet
    assert opp["dora_han"] == 1   # one visible 5m dora in chi
    assert opp["han"] == opp["yaku_han"] + opp["dora_han"]
