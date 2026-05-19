"""Call-opportunity analysis tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.calls import analyze_call
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


def _option(result: dict, action: str) -> dict:
    return next(o for o in result["options"] if o["action"] == action)


# ---- Pon -----------------------------------------------------------------


def test_pon_yakuhai_dragon_is_recommended():
    # Hand has a pair of Haku (5z) and is at moderate shanten; an opponent
    # discards Haku -> Pon should be strongly recommended.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z2m4m", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5z"), discarder_seat=2)
    pon = _option(res, "pon")
    assert pon["legal"] is True
    assert pon["recommended"] is True
    assert pon["yaku_hint"] == "yakuhai"
    assert "Dragon" in " ".join(pon["notes"])
    assert res["recommended_action"] == "pon"


def test_pon_seat_wind_is_recommended():
    # Seat wind = South (2z); user has 2 of South; opponent discards South.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s2z2z2m3m", round_wind="1z", seat_wind="2z"
    )
    res = analyze_call(state, _id("2z"), discarder_seat=2)
    pon = _option(res, "pon")
    assert pon["legal"] and pon["recommended"]
    assert pon["yaku_hint"] == "yakuhai"
    assert "seat wind" in " ".join(pon["notes"]).lower()


def test_pon_non_yakuhai_far_from_tenpai_not_recommended():
    # Pair of 5m, otherwise scattered; pon doesn't help and opens the hand.
    state = GameState.from_hand(
        "1m3m5m5m9m1p3p5p7p9p1s3s5s", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5m"), discarder_seat=2)
    pon = _option(res, "pon")
    assert pon["legal"] is True
    assert pon["recommended"] is False
    assert pon["score"] < 60


def test_pon_illegal_without_pair():
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z6z7z2m", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5z"), discarder_seat=2)
    pon = _option(res, "pon")
    assert pon["legal"] is False


# ---- Chi -----------------------------------------------------------------


def test_chi_only_from_kamicha():
    state = GameState.from_hand(
        "1m2m4p5p6p7s8s9s5z5z6z6z7z", round_wind="1z", seat_wind="1z"
    )
    # Toimen (seat 2) discards 3m -> Chi must be illegal.
    res = analyze_call(state, _id("3m"), discarder_seat=2)
    chi = _option(res, "chi")
    assert chi["legal"] is False
    # Kamicha (seat 3) discards 3m -> Chi is legal.
    res = analyze_call(state, _id("3m"), discarder_seat=3)
    chi = _option(res, "chi")
    assert chi["legal"] is True


def test_chi_picks_best_shanten_shape():
    # Hand has both 1m2m and 4m5m; kamicha discards 3m -> the engine should
    # consider the shape that gives the best shanten.
    state = GameState.from_hand(
        "1m2m4m5m4p5p6p7s8s9s5z5z6z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("3m"), discarder_seat=3)
    chi = _option(res, "chi")
    assert chi["legal"] is True
    assert chi["shanten_after"] is not None
    assert chi["shanten_after"] <= chi["shanten_before"]


# ---- Kan -----------------------------------------------------------------


def test_kan_illegal_without_three_copies():
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z2m4m", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5z"), discarder_seat=2)
    kan = _option(res, "kan")
    assert kan["legal"] is False


def test_kan_yakuhai_recommended():
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z5z2m", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5z"), discarder_seat=2)
    kan = _option(res, "kan")
    assert kan["legal"] is True
    assert kan["yaku_hint"] == "yakuhai"
    assert kan["recommended"] is True


# ---- Ron -----------------------------------------------------------------


def test_ron_when_winning():
    # Tenpai shanpon waiting on 1z/2z; opponent discards 1z -> Ron available.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("1z"), discarder_seat=2)
    ron = _option(res, "ron")
    assert ron["legal"] is True
    assert ron["recommended"] is True
    assert res["recommended_action"] == "ron"


def test_ron_not_legal_when_not_winning():
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z6z6z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("3m"), discarder_seat=2)
    ron = _option(res, "ron")
    assert ron["legal"] is False


# ---- Pass + ordering -----------------------------------------------------


def test_pass_always_legal_default():
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z6z6z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("8z"[:1] + "p"), discarder_seat=2)
    p = _option(res, "pass")
    assert p["legal"] is True


def test_recommended_action_prefers_ron_over_pon():
    # Both pon (yakuhai 5z) AND ron (winning on 5z, e.g. shanpon) available.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s5z5z2z2z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5z"), discarder_seat=2)
    assert res["recommended_action"] == "ron"


# ---- Riichi pressure -----------------------------------------------------


def test_riichi_threat_dampens_chi_recommendation():
    state = GameState.from_hand(
        "1m2m4m5m4p5p6p7s8s9s5z5z6z", round_wind="1z", seat_wind="1z"
    )
    state.opponents[0].riichi = True
    state.opponents[0].riichi_discard_index = 0
    res = analyze_call(state, _id("3m"), discarder_seat=3)
    chi = _option(res, "chi")
    # Even when chi reduces shanten, the riichi pressure should keep it from
    # being "recommended" outright unless the gain is large.
    assert any("riichi" in n.lower() for n in chi["notes"])
