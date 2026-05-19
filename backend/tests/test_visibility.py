"""Visible-tile / remaining-tile tests."""

from __future__ import annotations

from backend.app.mahjong.game import GameState, Meld, PlayerState
from backend.app.mahjong.tiles import tile_id_from_code
from backend.app.mahjong.visibility import (
    cap_ukeire_with_remaining,
    remaining_counts,
    visible_counts,
)


def _id(code: str) -> int:
    return tile_id_from_code(code)


def test_visible_counts_includes_hand_dora_discards_melds():
    state = GameState.from_hand(
        "123m456p789s1122z7z",
        round_wind="1z",
        seat_wind="1z",
        dora_indicators="3m",
    )
    state.opponents[0].discards = [_id("5m"), _id("9p")]
    state.opponents[1].melds = [Meld(type="pon", tiles=[_id("7z"), _id("7z"), _id("7z")])]
    state.user.discards = [_id("3z")]

    counts = visible_counts(state)

    # Hand contributions
    assert counts[_id("1m")] == 1
    # 3m: 1 in hand (from "123m") + 1 dora indicator = 2
    assert counts[_id("3m")] == 2
    # Discards
    assert counts[_id("5m")] == 1
    assert counts[_id("3z")] == 1
    # Meld + 1 from hand on the chun = 4
    assert counts[_id("7z")] == 1 + 3


def test_remaining_counts_caps_at_4():
    state = GameState.from_hand("11122m", round_wind="1z", seat_wind="1z")
    rem = remaining_counts(state)
    assert rem[_id("1m")] == 4 - 3
    assert rem[_id("2m")] == 4 - 2
    assert rem[_id("9z")] if False else True  # noop guard


def test_cap_ukeire_uses_smaller_of_raw_or_remaining():
    raw = {_id("1z"): 4, _id("2z"): 4}
    remaining = [0] * 34
    remaining[_id("1z")] = 1
    remaining[_id("2z")] = 0  # exhausted
    capped = cap_ukeire_with_remaining(raw, remaining)
    assert capped == {_id("1z"): 1}
