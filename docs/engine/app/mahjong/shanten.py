"""Shanten (tiles-to-tenpai) calculation.

Returns the lowest of three independent calculators:

* normal hand        -> 4 melds + 1 pair structure
* chiitoitsu         -> seven pairs
* kokushi musou      -> thirteen orphans

Conventions
-----------
* ``-1`` means the hand is already a winning shape (agari).
* ``0`` means tenpai (one tile away from winning).
* Larger numbers mean further from tenpai.
* The hand may have 13 or 14 tiles. For 14 tiles, the result is the lowest
  shanten achievable after the best discard.

Algorithm (normal hand)
-----------------------
For a fixed candidate "head" pair (or no head), enumerate every way to
decompose the remaining tiles into complete melds (triplets / sequences)
and partial melds / pairs ("taatsu"). For each decomposition::

    shanten = 8 - 2*sets - min(partials, 4 - sets) - (1 if head else 0)

The minimum across all decompositions and head choices is the answer.

The recursion processes the 34 tile slots left-to-right. Branches are
ordered (set first, then partials, then "drop") so that good solutions are
found early and weaker branches are pruned by the running best.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from .tiles import NUM_TILES, YAOCHU_IDS


@dataclass(frozen=True)
class ShantenBreakdown:
    """Per-form breakdown used by the analysis layer for explanations."""

    overall: int
    normal: int
    chiitoitsu: int
    kokushi: int

    @property
    def best_form(self) -> str:
        if self.overall == self.kokushi and self.kokushi <= self.chiitoitsu and self.kokushi <= self.normal:
            return "kokushi"
        if self.overall == self.chiitoitsu and self.chiitoitsu <= self.normal:
            return "chiitoitsu"
        return "normal"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_shanten_cache: dict[Tuple, ShantenBreakdown] = {}


def calculate_shanten(counts: Sequence[int], open_melds_count: int = 0) -> int:
    """Return the shanten number for ``counts`` (length 34).

    :param open_melds_count: Number of open melds the hand owns (chi / pon /
        open kan / ankan). Each one counts as a complete mentsu and reduces
        the work the closed hand has to do.
    """
    return calculate_shanten_breakdown(counts, open_melds_count).overall


def calculate_shanten_breakdown(
    counts: Sequence[int], open_melds_count: int = 0
) -> ShantenBreakdown:
    """Return per-form breakdown plus the minimum (overall)."""
    if len(counts) != NUM_TILES:
        raise ValueError(f"counts must have length {NUM_TILES}, got {len(counts)}")
    if not 0 <= open_melds_count <= 4:
        raise ValueError(
            f"open_melds_count must be in 0..4, got {open_melds_count}"
        )

    key = (tuple(counts), open_melds_count)
    cached = _shanten_cache.get(key)
    if cached is not None:
        return cached

    n = sum(counts)
    # The closed hand size depends on how many open melds we already own.
    # Each meld effectively replaces three concealed tiles, so valid closed
    # totals are (13 - 3K), (14 - 3K). We accept any non-negative count up
    # to 14 to make incremental UIs less brittle.
    if n < 0 or n > 14:
        raise ValueError(f"hand size {n} is out of supported range (0..14)")

    normal = _shanten_normal(list(counts), open_melds_count)
    if open_melds_count > 0:
        # Chiitoitsu and kokushi require a fully concealed hand.
        chiitoi = 99
        kokushi = 99
    else:
        chiitoi = _shanten_chiitoitsu(counts)
        kokushi = _shanten_kokushi(counts)
    overall = min(normal, chiitoi, kokushi)
    breakdown = ShantenBreakdown(overall=overall, normal=normal, chiitoitsu=chiitoi, kokushi=kokushi)
    _shanten_cache[key] = breakdown
    return breakdown


def clear_cache() -> None:
    """For tests / long-running processes."""
    _shanten_cache.clear()


# ---------------------------------------------------------------------------
# Chiitoitsu and kokushi
# ---------------------------------------------------------------------------


def _shanten_chiitoitsu(counts: Sequence[int]) -> int:
    """Seven pairs. Each pair must be a different tile type."""
    pairs = 0
    types = 0
    for c in counts:
        if c >= 1:
            types += 1
        if c >= 2:
            pairs += 1
    # Need 7 pairs of 7 different types. Excess copies (>=3) don't help.
    shanten = 6 - pairs
    if types < 7:
        shanten += 7 - types
    return shanten


def _shanten_kokushi(counts: Sequence[int]) -> int:
    """Thirteen-orphans: one of each terminal/honor and one extra pair."""
    types = 0
    has_pair = False
    for tid in YAOCHU_IDS:
        c = counts[tid]
        if c >= 1:
            types += 1
        if c >= 2:
            has_pair = True
    return 13 - types - (1 if has_pair else 0)


# ---------------------------------------------------------------------------
# Normal (4 melds + 1 pair) shanten
# ---------------------------------------------------------------------------


def _shanten_normal(counts: list[int], open_melds_count: int = 0) -> int:
    """Best shanten over all (head, decomposition) choices.

    With ``open_melds_count = K``, K mentsu are already committed, so the
    closed-hand decomposition only needs ``(4 - K)`` mentsu plus the head.
    """
    best = [8]
    available_meld_slots = max(0, 4 - open_melds_count)

    # Try each candidate head. Pairs are rare so this is cheap.
    for head_id in range(NUM_TILES):
        if counts[head_id] >= 2:
            counts[head_id] -= 2
            _decompose(counts, 0, 0, 0, True, best, open_melds_count, available_meld_slots)
            counts[head_id] += 2

    # Also consider no head at all (e.g. perfectly closed sets but no pair).
    _decompose(counts, 0, 0, 0, False, best, open_melds_count, available_meld_slots)

    return best[0]


def _decompose(
    counts: list[int],
    idx: int,
    sets: int,
    partials: int,
    has_head: bool,
    best: list[int],
    open_melds_count: int,
    available_meld_slots: int,
) -> None:
    """Branch over the remaining tiles. Updates ``best[0]`` in place."""
    # Fast-forward over empty slots.
    while idx < NUM_TILES and counts[idx] == 0:
        idx += 1

    if idx >= NUM_TILES:
        cap = max(0, available_meld_slots - sets)
        capped = partials if partials <= cap else cap
        # Open melds count as already-completed sets worth 2 each.
        shanten = 8 - 2 * (sets + open_melds_count) - capped - (1 if has_head else 0)
        if shanten < best[0]:
            best[0] = shanten
        return

    # ----- branch 1: complete melds (always worth trying) ---------------
    if counts[idx] >= 3:
        counts[idx] -= 3
        _decompose(counts, idx, sets + 1, partials, has_head, best,
                   open_melds_count, available_meld_slots)
        counts[idx] += 3

    if idx < 27:  # numbered suit -> sequences are possible
        suit_end = (idx // 9 + 1) * 9
        if idx + 2 < suit_end and counts[idx + 1] >= 1 and counts[idx + 2] >= 1:
            counts[idx] -= 1
            counts[idx + 1] -= 1
            counts[idx + 2] -= 1
            _decompose(counts, idx, sets + 1, partials, has_head, best,
                       open_melds_count, available_meld_slots)
            counts[idx] += 1
            counts[idx + 1] += 1
            counts[idx + 2] += 1

    # ----- branch 2: partial melds (only if we still have meld slots) ---
    if sets + partials < available_meld_slots:
        if counts[idx] >= 2:
            counts[idx] -= 2
            _decompose(counts, idx, sets, partials + 1, has_head, best,
                       open_melds_count, available_meld_slots)
            counts[idx] += 2

        if idx < 27:
            suit_end = (idx // 9 + 1) * 9
            if idx + 1 < suit_end and counts[idx + 1] >= 1:
                counts[idx] -= 1
                counts[idx + 1] -= 1
                _decompose(counts, idx, sets, partials + 1, has_head, best,
                           open_melds_count, available_meld_slots)
                counts[idx] += 1
                counts[idx + 1] += 1
            if idx + 2 < suit_end and counts[idx + 2] >= 1:
                counts[idx] -= 1
                counts[idx + 2] -= 1
                _decompose(counts, idx, sets, partials + 1, has_head, best,
                           open_melds_count, available_meld_slots)
                counts[idx] += 1
                counts[idx + 2] += 1

    # ----- branch 3: drop this single tile (treat as isolated) ----------
    counts[idx] -= 1
    _decompose(counts, idx, sets, partials, has_head, best,
               open_melds_count, available_meld_slots)
    counts[idx] += 1
