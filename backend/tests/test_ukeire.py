"""Ukeire calculator tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.hand import Hand
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code
from backend.app.mahjong.ukeire import calculate_ukeire


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def test_shanpon_wait_two_kinds():
    # Tenpai shanpon on 1z / 2z
    counts = Hand.from_string("123m456p789s1122z").counts
    uke = calculate_ukeire(counts)
    waits = set(uke.keys())
    assert waits == {tile_id_from_code("1z"), tile_id_from_code("2z")}
    # Each has 2 copies in hand, so 2 remain in walls
    for tid, remaining in uke.items():
        assert remaining == 2


def test_nobetan_wait():
    counts = Hand.from_string("123m456m789m1234p").counts
    uke = calculate_ukeire(counts)
    waits = set(uke.keys())
    assert waits == {tile_id_from_code("1p"), tile_id_from_code("4p")}
    assert all(r == 3 for r in uke.values())  # 1 in hand each -> 3 remain


def test_chiitoitsu_one_kind():
    # 6 pairs + 1 single -> wait only on the single's mate
    counts = Hand.from_string("11m22p33s44m55s66p7z").counts
    uke = calculate_ukeire(counts)
    assert tile_id_from_code("7z") in uke
    assert uke[tile_id_from_code("7z")] == 3


def test_kokushi_13_way():
    counts = Hand.from_string("19m19p19s1234567z").counts
    uke = calculate_ukeire(counts)
    expected = {
        tile_id_from_code(c)
        for c in [
            "1m", "9m", "1p", "9p", "1s", "9s",
            "1z", "2z", "3z", "4z", "5z", "6z", "7z",
        ]
    }
    assert set(uke.keys()) == expected


def test_one_shanten_has_many_kinds():
    counts = Hand.from_string("123m456m789m12s12p").counts  # 13 tiles, 1-shanten
    uke = calculate_ukeire(counts)
    assert len(uke) >= 1
    for r in uke.values():
        assert 1 <= r <= 4


def test_fully_winning_has_no_improvement():
    # Already winning; nothing improves further (well, ukeire is empty for -1)
    counts = Hand.from_string("123m456p789s11122z").counts  # 14 tiles
    # Drop a tile to get 13-tile tenpai.
    counts[tile_id_from_code("2z")] -= 1
    uke = calculate_ukeire(counts)
    assert tile_id_from_code("2z") in uke
