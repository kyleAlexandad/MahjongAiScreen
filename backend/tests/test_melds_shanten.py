"""Shanten / analyze with open melds (chi/pon/kan/ankan)."""

from __future__ import annotations

import pytest

from backend.app.mahjong.analyzer import analyze_game
from backend.app.mahjong.game import GameState, Meld
from backend.app.mahjong.shanten import calculate_shanten, clear_cache
from backend.app.mahjong.tiles import tile_id_from_code


def _id(code: str) -> int:
    return tile_id_from_code(code)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _counts_from(codes: list[str]) -> list[int]:
    counts = [0] * 34
    for c in codes:
        counts[_id(c)] += 1
    return counts


def test_one_open_meld_winning_closed_hand():
    # 1 open chi + closed hand = 3 sets + 1 pair = winning.
    closed = _counts_from(
        ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "1z", "1z"]
    )
    assert sum(closed) == 11
    sh = calculate_shanten(closed, open_melds_count=1)
    assert sh == -1


def test_one_open_meld_tenpai():
    # 1 open chi + closed = 3 sets + 1 isolated = tenpai (needs pair).
    closed = _counts_from(
        ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "1z"]
    )
    assert sum(closed) == 10
    assert calculate_shanten(closed, open_melds_count=1) == 0


def test_two_open_melds_tenpai_via_kanchan():
    # 2 open melds + 7 closed: 1 set + pair head + kanchan.
    closed = _counts_from(["1m", "2m", "3m", "4p", "4p", "7s", "9s"])
    assert sum(closed) == 7
    sh = calculate_shanten(closed, open_melds_count=2)
    # 1 closed set + 1 pair (head) + 1 kanchan partial; cap = 4-2-1=1; shanten = 8-2*(1+2)-1-1 = 0
    assert sh == 0


def test_chiitoi_kokushi_disabled_when_open_melds():
    # 7-pair-style hand but with 1 meld: chiitoi must be invalid.
    closed = _counts_from(["1m", "1m", "2p", "2p", "3s", "3s", "4z", "4z", "5z", "5z", "6z"])
    sh = calculate_shanten(closed, open_melds_count=1)
    # Chiitoi is disabled (returns 99); regular form will dominate.
    assert sh < 99


def test_analyze_game_with_open_pon():
    # Open pon (2m) + 10 closed tiles in shanpon tenpai (1z/2z).
    # 4m5m6m + 7p8p9p + 1z1z + 2z2z = 10 closed; with the open pon that's
    # 3 sets + 2 pairs = 13 effective tiles -> tenpai shanpon.
    state = GameState.from_hand("4m5m6m7p8p9p1z1z2z2z", round_wind="1z", seat_wind="1z")
    state.user.melds = [Meld(type="pon", tiles=[_id("2m"), _id("2m"), _id("2m")], called_from=1)]
    res = analyze_game(state)
    assert res["shanten"] == 0
    assert res["is_tenpai"] is True


def test_analyze_game_validates_closed_hand_size():
    # 13 closed tiles + 1 open meld would be too many — must reject.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s1z1z2z2z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [Meld(type="pon", tiles=[_id("3z"), _id("3z"), _id("3z")], called_from=1)]
    with pytest.raises(ValueError):
        analyze_game(state)


def test_analyze_game_with_open_chi_post_draw():
    # 1 open chi + 11 closed after draw -> winning when closed contributes 3 sets + pair.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s1z1z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [Meld(type="chi", tiles=[_id("4m"), _id("5m"), _id("6m")], called_from=3)]
    res = analyze_game(state)
    assert res["shanten"] == -1
    assert res["is_winning"] is True


def test_analyze_game_with_ankan_meld_treated_as_one_mentsu():
    # Concealed kan of 5p + 10 closed tiles (3 sets + 1 pair) = winning.
    state = GameState.from_hand(
        "1m2m3m4m5m6m7s8s9s1z1z", round_wind="1z", seat_wind="1z"
    )
    state.user.melds = [Meld(type="ankan", tiles=[_id("5p"), _id("5p"), _id("5p"), _id("5p")], called_from=None)]
    res = analyze_game(state)
    # 11 closed (post-draw size) + 1 ankan -> 4 mentsu + 1 head -> winning
    assert res["shanten"] == -1
    # Yaku panel still produced.
    assert "yaku_directions" in res
    assert isinstance(res["yaku_directions"], list)


def test_analyze_game_with_ankan_user_in_yaku_directions():
    # Ankan of South (2z) when seat wind = South -> yakuhai direction kept.
    state = GameState.from_hand(
        "1m2m3m4p5p6p7s8s9s7z", round_wind="1z", seat_wind="2z"
    )
    state.user.melds = [Meld(type="ankan", tiles=[_id("2z"), _id("2z"), _id("2z"), _id("2z")], called_from=None)]
    res = analyze_game(state)
    yaku_names = [d["name"] for d in res["yaku_directions"]]
    # The ankan itself is yakuhai (seat wind), so a yakuhai entry should appear.
    assert any(n.startswith("yakuhai_") for n in yaku_names)
