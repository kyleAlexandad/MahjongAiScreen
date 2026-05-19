"""Strict-legality helper tests.

These mirror what the frontend does in its drop-zone disabling logic, so
both layers stay in sync.
"""

from __future__ import annotations

import pytest

from backend.app.mahjong.game import GameState, Meld
from backend.app.mahjong.legality import (
    can_user_ankan,
    can_user_open_kan,
    can_user_pon,
    get_legal_chi_options,
    is_chi_seat_legal,
    opponent_call_feasible,
    remaining_unseen,
    user_ankan_candidates,
)
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code as _id


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _state(hand: str, *, aka_in_hand: int = 0, **kwargs) -> GameState:
    s = GameState.from_hand(hand, round_wind="1z", seat_wind="1z", **kwargs)
    s.aka_in_hand = aka_in_hand
    return s


# ---------------------------------------------------------------------------
# Pon
# ---------------------------------------------------------------------------


def test_pon_legal_with_two_matching_tiles():
    s = _state("1m2m3m4p5p6p7s8s9s9m9m2z3z4z")  # 14 incl. pair of 9m
    assert can_user_pon(s, _id("9m")) is True


def test_pon_illegal_with_one_tile():
    s = _state("1m2m3m4p5p6p7s8s9s9m1z2z3z4z")  # 14, only one 9m
    assert can_user_pon(s, _id("9m")) is False


def test_pon_legal_with_red_5_plus_normal_5():
    # 14 tiles, two of them are 5m (one normal + one red). The aka identity
    # isn't tracked in the 34-count vector — only base-tile counts matter
    # for pon legality, so red 5m + normal 5m IS a valid pair.
    s = _state("1m2m3m4p5p6p7s8s9s5m5m1z2z3z", aka_in_hand=1)
    assert can_user_pon(s, _id("5m")) is True


def test_pon_illegal_with_only_one_red_5():
    s = _state("1m2m3m4p5p6p7s8s9s5m1z2z3z4z", aka_in_hand=1)
    assert can_user_pon(s, _id("5m")) is False  # only one 5m total


# ---------------------------------------------------------------------------
# Open kan (daiminkan)
# ---------------------------------------------------------------------------


def test_open_kan_legal_with_three_tiles():
    s = _state("1m2m3m4p5p6p7s8s9s9m9m9m1z2z")
    assert can_user_open_kan(s, _id("9m")) is True


def test_open_kan_illegal_with_two_tiles():
    s = _state("1m2m3m4p5p6p7s8s9s9m9m1z2z3z")
    assert can_user_open_kan(s, _id("9m")) is False


def test_open_kan_legal_with_normal5_normal5_red5():
    # 5m count = 3 in hand (one of which is red).
    s = _state("1m2m3m4p5p6p7s8s9s5m5m5m1z2z", aka_in_hand=1)
    assert can_user_open_kan(s, _id("5m")) is True


# ---------------------------------------------------------------------------
# Chi
# ---------------------------------------------------------------------------


def test_chi_seat_legality():
    # User (seat 0) kamicha is seat 3.
    assert is_chi_seat_legal(0, 3) is True
    assert is_chi_seat_legal(0, 1) is False
    assert is_chi_seat_legal(0, 2) is False
    # Seat 2's kamicha is seat 1.
    assert is_chi_seat_legal(2, 1) is True
    assert is_chi_seat_legal(2, 0) is False


def test_chi_legal_123_shape():
    s = _state("1m2m4p5p6p7s8s9s9m9m1z2z3z")
    opts = get_legal_chi_options(s, _id("3m"), discarder_seat=3)
    assert (0, 1) in opts  # 1m+2m+3m


def test_chi_legal_234_shape():
    s = _state("2m4m4p5p6p7s8s9s9m9m1z2z3z")
    opts = get_legal_chi_options(s, _id("3m"), discarder_seat=3)
    assert (1, 3) in opts  # 2m+4m around 3m


def test_chi_legal_345_shape_with_red_5():
    # User has 4m + red 5m -> chi 3m-4m-5m must be legal (red 5m has base id 4).
    s = _state("4m5m4p5p6p7s8s9s9m9m1z2z3z", aka_in_hand=1)
    opts = get_legal_chi_options(s, _id("3m"), discarder_seat=3)
    assert (3, 4) in opts  # 4m + 5m


def test_chi_illegal_when_missing_required_tile():
    s = _state("1m4p5p6p7s8s9s9m9m1z2z3z4z")
    opts = get_legal_chi_options(s, _id("3m"), discarder_seat=3)
    assert opts == []  # no 2m to complete any 3m chi


def test_chi_illegal_for_honors():
    s = _state("1z2z4p5p6p7s8s9s9m9m1m2m3m")
    opts = get_legal_chi_options(s, _id("3z"), discarder_seat=3)
    assert opts == []


def test_chi_illegal_from_non_kamicha():
    s = _state("1m2m4p5p6p7s8s9s9m9m1z2z3z")
    # Toimen (seat 2) is NOT kamicha -> chi must be illegal even though the
    # tiles are present.
    opts = get_legal_chi_options(s, _id("3m"), discarder_seat=2)
    assert opts == []
    opts2 = get_legal_chi_options(s, _id("3m"), discarder_seat=1)
    assert opts2 == []


# ---------------------------------------------------------------------------
# Ankan
# ---------------------------------------------------------------------------


def test_ankan_candidates_returns_only_quads():
    # 1m * 4 + 14-tile hand sized correctly.
    s = _state("1m1m1m1m4p5p6p7s8s9s9m1z2z")
    cands = user_ankan_candidates(s)
    assert _id("1m") in cands
    assert can_user_ankan(s, _id("1m")) is True


def test_ankan_illegal_when_not_four():
    s = _state("1m1m1m4p5p6p7s8s9s9m9m1z2z")
    assert can_user_ankan(s, _id("1m")) is False


# ---------------------------------------------------------------------------
# Opponent-call tile-pool feasibility
# ---------------------------------------------------------------------------


def test_remaining_unseen_subtracts_every_visible_source():
    s = _state("1m2m3m4p5p6p7s8s9s9m9m1z2z3z")
    rem = remaining_unseen(s)
    assert rem[_id("9m")] == 2  # two 9m in hand -> 2 unseen
    assert rem[_id("5s")] == 4  # untouched


def test_opponent_pon_feasible_when_two_copies_unseen():
    # Only the called tile (in shimocha's river) is visible -> 3 unseen,
    # enough for an opponent to hold the 2 hidden copies a pon needs.
    s = _state("1m2m3m4p5p6p7s8s9s1z2z3z4z5z")
    s.opponents[0].discards = [_id("7z")]
    assert opponent_call_feasible(s, "pon", _id("7z")) is True


def test_opponent_pon_infeasible_when_user_holds_the_rest():
    # User holds two 7z; shimocha discards a third. Only one 7z is unseen,
    # so no opponent can possibly hold the two hidden copies a pon needs.
    s = _state("1m2m3m4p5p6p7s8s9s7z7z1z2z3z")
    s.opponents[0].discards = [_id("7z")]
    assert opponent_call_feasible(s, "pon", _id("7z")) is False


def test_opponent_kan_needs_three_unseen():
    s = _state("1m2m3m4p5p6p7s8s9s7z1z2z3z4z")  # one 7z in hand
    s.opponents[0].discards = [_id("7z")]       # one 7z visible in river
    # 4 - 2 visible = 2 unseen; daiminkan needs 3 -> infeasible.
    assert opponent_call_feasible(s, "kan", _id("7z")) is False
    s2 = _state("1m2m3m4p5p6p7s8s9s1z2z3z4z5z")
    s2.opponents[0].discards = [_id("7z")]      # only the called tile visible
    assert opponent_call_feasible(s2, "kan", _id("7z")) is True


def test_opponent_chi_needs_each_run_tile_unseen():
    # Kamicha discards 3m; opponent would chi with 4m+5m. Four 4m are
    # already visible (a kabe), so the opponent cannot hold a hidden 4m.
    s = GameState.from_hand(
        "4m4m4m4m1p2p3p7s8s9s1z2z3z", round_wind="1z", seat_wind="1z"
    )
    s.opponents[0].discards = [_id("3m")]
    assert opponent_call_feasible(s, "chi", _id("3m"), (_id("4m"), _id("5m"))) is False
    # 4m+? not blocked when copies remain (5m/6m run).
    assert opponent_call_feasible(s, "chi", _id("3m"), (_id("1m"), _id("2m"))) is True


def test_opponent_call_feasible_rejects_bad_input():
    s = _state("1m2m3m4p5p6p7s8s9s9m9m1z2z3z")
    assert opponent_call_feasible(s, "pon", -1) is False
    assert opponent_call_feasible(s, "chi", _id("3m"), (_id("3m"), _id("3m"))) is False
    assert opponent_call_feasible(s, "unknown", _id("3m")) is True  # never over-blocks
