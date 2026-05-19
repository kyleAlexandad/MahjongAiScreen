"""Ukeire (effective tiles) calculation for a 13-tile hand."""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from .tiles import NUM_TILES
from .shanten import calculate_shanten


def calculate_ukeire(
    counts: Sequence[int],
    current_shanten: int | None = None,
    remaining: Optional[Sequence[int]] = None,
    open_melds_count: int = 0,
) -> Dict[int, int]:
    """Tiles that strictly reduce shanten when drawn.

    :param counts: Length-34 count vector for a hand of 13 tiles.
    :param current_shanten: If already known, pass it to avoid recomputation.
    :param remaining: Optional length-34 vector of tiles still **possibly**
        available (after subtracting all visible tiles in the world). When
        provided, each ukeire copy count is capped by the corresponding
        remaining value. When omitted the cap defaults to ``4 - in_hand``.
    :param open_melds_count: Number of open melds (chi/pon/kan/ankan) already
        owned by this hand.
    :return: Mapping ``{tile_id: copies_likely_remaining}``.
    """
    if len(counts) != NUM_TILES:
        raise ValueError(f"counts must have length {NUM_TILES}")
    if remaining is not None and len(remaining) != NUM_TILES:
        raise ValueError(f"remaining must have length {NUM_TILES}")

    counts = list(counts)
    if current_shanten is None:
        current_shanten = calculate_shanten(counts, open_melds_count)

    result: Dict[int, int] = {}
    for tid in range(NUM_TILES):
        if counts[tid] >= 4:
            continue
        counts[tid] += 1
        new_shanten = calculate_shanten(counts, open_melds_count)
        counts[tid] -= 1
        if new_shanten < current_shanten:
            cap = remaining[tid] if remaining is not None else 4 - counts[tid]
            if cap > 0:
                result[tid] = cap
    return result


def total_ukeire(ukeire: Dict[int, int]) -> int:
    return sum(ukeire.values())
