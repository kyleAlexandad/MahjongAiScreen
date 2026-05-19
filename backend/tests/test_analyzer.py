"""Analyzer (discard recommendation) tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.analyzer import analyze_hand, recommend_discards
from backend.app.mahjong.hand import Hand
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def test_analyze_13_tile_tenpai():
    res = analyze_hand(Hand.from_string("123m456p789s1122z").counts)
    assert res["tile_count"] == 13
    assert res["shanten"] == 0
    assert res["is_tenpai"] is True
    assert res["is_winning"] is False
    assert res["ukeire_count"] == 4  # 2 of each of 1z and 2z remaining
    assert "tenpai" in res["explanation"].lower()


def test_analyze_14_tile_recommends_clear_discard():
    # 14-tile hand: 13-tile shanpon tenpai + 1 isolated 7z (Chun).
    # The 7z is obvious dead weight, so the best discard should be 7z and the
    # resulting 13-tile hand should be tenpai (shanten 0).
    res = analyze_hand(Hand.from_string("123m456p789s1122z7z").counts)
    assert res["tile_count"] == 14
    best = res["best_discard"]
    assert best is not None
    assert best["tile_code"] == "7z"
    assert best["shanten_after"] == 0
    assert "Discard" in res["explanation"]


def test_analyze_14_tile_sorted_ranking():
    res = analyze_hand(Hand.from_string("123m456p789s1122z7z").counts)
    discards = res["discards"]
    # Sorted by (shanten_after asc, ukeire_count desc).
    for a, b in zip(discards, discards[1:]):
        assert (a["shanten_after"], -a["ukeire_count"]) <= (
            b["shanten_after"],
            -b["ukeire_count"],
        )


def test_recommend_discards_returns_one_per_distinct_tile():
    # 14-tile hand: 4+4+2+2+2 = 14, with 5 distinct tile types.
    counts = Hand.from_string("1111m2222m33p44p55p").counts
    assert sum(counts) == 14
    candidates = recommend_discards(counts)
    distinct_in_hand = sum(1 for c in counts if c > 0)
    assert len(candidates) == distinct_in_hand


def test_analyze_winning_14_hand():
    res = analyze_hand(Hand.from_string("11122233344455m").counts)
    assert res["shanten"] == -1
    assert res["is_winning"] is True


def test_explanation_mentions_short_name():
    res = analyze_hand(Hand.from_string("123m456p789s1122z7z").counts)
    # 7z's short name is "Rd" (Chun); the analyser uses short names to keep
    # the panel compact.
    assert "Rd" in res["explanation"] or "7z" in res["explanation"]


def test_size_validation():
    with pytest.raises(ValueError):
        analyze_hand(Hand.from_string("123m").counts)
