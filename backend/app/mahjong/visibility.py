"""Compute what is visible at the table from a :class:`GameState`.

"Visible" tiles are everything the user can definitely see:

* their own concealed hand
* every player's discard piles
* every open meld (chi / pon / kan); ankan also fully visible
* dora indicators

Anything else (opponents' concealed hands, dead wall apart from indicators,
remaining wall) is unknown.

The output is a 34-int counts vector. ``ukeire`` and the defense module
both consume it.
"""

from __future__ import annotations

from typing import Sequence

from .game import GameState
from .tiles import NUM_TILES


def visible_counts(state: GameState) -> list[int]:
    """Tiles publicly visible on the table.

    Includes the user's concealed hand because it is information *they*
    have. The total may exceed 4 only if the input game-state is invalid
    (which we deliberately don't enforce here so the helper stays cheap).
    """
    counts = [0] * NUM_TILES
    for tid in state.hand:
        counts[tid] += 1
    for tid in state.dora_indicators:
        counts[tid] += 1
    for player in state.all_players():
        for tid in player.discards:
            counts[tid] += 1
        for meld in player.melds:
            for tid in meld.tiles:
                counts[tid] += 1
    return counts


def remaining_counts(state: GameState) -> list[int]:
    """How many copies of each tile *might still* be in walls / hands.

    Used to compute realistic ukeire numbers (each effective tile is at
    most ``remaining[tid]`` because the rest are already on the table).
    """
    visible = visible_counts(state)
    return [max(0, 4 - v) for v in visible]


def cap_ukeire_with_remaining(
    ukeire: dict[int, int], remaining: Sequence[int]
) -> dict[int, int]:
    """Replace each ukeire value with the smaller of (raw, remaining).

    This shrinks the count of e.g. 3p ukeire from 3 to 1 if two 3p are
    already discarded.
    """
    capped: dict[int, int] = {}
    for tid, raw in ukeire.items():
        cap = remaining[tid]
        if cap > 0:
            capped[tid] = min(raw, cap)
    return capped
