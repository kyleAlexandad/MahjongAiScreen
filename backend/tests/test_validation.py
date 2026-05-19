"""Tile-pool sanity validation tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.game import GameState, Meld, PlayerState
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code as _id
from backend.app.mahjong.validation import (
    count_visible_tiles,
    validate_tile_pool,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def _state(hand: str = "1m2m3m4p5p6p7s8s9s5z6z7z1m", *, aka_in_hand: int = 0, **kwargs) -> GameState:
    s = GameState.from_hand(hand, round_wind="1z", seat_wind="1z", **kwargs)
    s.aka_in_hand = aka_in_hand
    return s


# ---------------------------------------------------------------------------
# count_visible_tiles
# ---------------------------------------------------------------------------


def test_count_visible_includes_hand_dora_discards_melds():
    # 14-tile hand contains 1m × 3 and 9m × 1, plus filler.
    s = _state("1m1m1m4p5p6p7s8s9s9m5z6z7z2m")
    s.dora_indicators = [_id("1m")]  # +1 1m
    s.opponents[0].discards = [_id("2m")]  # +1 2m discarded
    s.opponents[1].melds = [Meld(type="pon", tiles=[_id("9m")] * 3)]
    counts = count_visible_tiles(s)
    assert counts[_id("1m")] == 3 + 1            # 3 in hand + 1 indicator
    assert counts[_id("9m")] == 1 + 3            # 1 in hand + 3 in pon
    assert counts[_id("2m")] == 1 + 1            # 1 in hand + 1 in opp river


def test_count_visible_does_not_doublecount_latest_discard():
    # The "latest discard" lives in the discarder's river by convention.
    # Adding the same tile to a separate field would double-count, but the
    # engine doesn't have such a field — the river IS the source of truth.
    s = _state("1m2m3m4p5p6p7s8s9s5z5z6z6z")
    s.opponents[0].discards = [_id("3m")]
    counts = count_visible_tiles(s)
    assert counts[_id("3m")] == 2  # 1 in hand + 1 in river


# ---------------------------------------------------------------------------
# validate_tile_pool
# ---------------------------------------------------------------------------


def test_validate_clean_state_returns_no_errors():
    s = _state()
    assert validate_tile_pool(s) == []


def test_validate_rejects_more_than_4_copies():
    s = _state("1m1m1m1m4p5p6p7s8s9s5z6z7z")
    s.opponents[0].discards = [_id("1m")]  # now 5 copies of 1m visible
    errors = validate_tile_pool(s)
    assert any("1m" in e and "max 4" in e for e in errors)


def test_validate_5m_3_normal_plus_1_red_is_fine():
    # 3 normal 5m + 1 red 5m visible across player + meld -> valid.
    s = _state("1m2m3m5m5m5m6p7s8s9s5z6z7z2m")  # 3 normal 5m in hand
    s.aka_in_hand = 0
    # Add a 5m red dora as a single-tile in a melded pon... actually a meld
    # with 3 tiles is needed; use a chi with red 5m for a clean test.
    s.opponents[0].melds = [
        Meld(type="chi", tiles=[_id("3m"), _id("4m"), _id("5m")], aka_count=1)
    ]
    # That's 3 normal in hand + 1 red in meld = 4 5m total, 1 red in suit.
    errors = validate_tile_pool(s)
    assert errors == [], errors


def test_validate_rejects_two_red_5m_in_melds():
    s = _state()
    s.opponents[0].melds = [
        Meld(type="chi", tiles=[_id("3m"), _id("4m"), _id("5m")], aka_count=1),
    ]
    s.opponents[1].melds = [
        Meld(type="chi", tiles=[_id("4m"), _id("5m"), _id("6m")], aka_count=1),
    ]
    errors = validate_tile_pool(s)
    # Either red-5m counted twice OR base-5m count > 4. Both are real errors.
    assert any("red 5m" in e for e in errors) or any("5m" in e and "max 4" in e for e in errors)


def test_validate_rejects_aka_in_hand_exceeding_5s_in_hand():
    # No 5m / 5p / 5s anywhere in the hand -> aka_in_hand=1 is impossible.
    s = _state("1m2m3m4p6p7p8p9p7s8s9s5z6z7z", aka_in_hand=1)
    errors = validate_tile_pool(s)
    assert any("aka_in_hand" in e for e in errors), errors


def test_validate_aka_in_hand_within_limits_passes():
    s = _state("1m2m3m4p5p6p7s8s9s5m5z6z7z1m", aka_in_hand=1)
    errors = validate_tile_pool(s)
    assert errors == [], errors
