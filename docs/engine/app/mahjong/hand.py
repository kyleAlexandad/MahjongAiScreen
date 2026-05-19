"""High-level :class:`Hand` container backed by a 34-int count vector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from .tiles import (
    NUM_TILES,
    counts_from_ids,
    counts_to_codes,
    parse_hand,
    tile_code,
    tile_id_from_code,
)


@dataclass
class Hand:
    """A 13- or 14-tile concealed hand.

    For Phase 1 we ignore open melds entirely; the engine assumes a fully
    concealed hand. The :attr:`counts` array is the canonical state.
    """

    counts: List[int] = field(default_factory=lambda: [0] * NUM_TILES)

    # ----- construction helpers -----------------------------------------

    @classmethod
    def empty(cls) -> "Hand":
        return cls()

    @classmethod
    def from_codes(cls, codes: Iterable[str]) -> "Hand":
        return cls(counts_from_ids(tile_id_from_code(c) for c in codes))

    @classmethod
    def from_ids(cls, ids: Iterable[int]) -> "Hand":
        return cls(counts_from_ids(ids))

    @classmethod
    def from_string(cls, text: str) -> "Hand":
        """Build a hand from a compact mpsz string like ``'123m456p11z'``."""
        return cls(counts_from_ids(parse_hand(text)))

    # ----- accessors ----------------------------------------------------

    def __len__(self) -> int:
        return sum(self.counts)

    def total(self) -> int:
        return sum(self.counts)

    def to_codes(self) -> List[str]:
        return counts_to_codes(self.counts)

    def to_string(self) -> str:
        """Return a compact mpsz string with one suit block per suit, e.g. '123m456p1z'."""
        groups = {"m": [], "p": [], "s": [], "z": []}
        for tid, c in enumerate(self.counts):
            for _ in range(c):
                code = tile_code(tid)
                groups[code[1]].append(code[0])
        out = []
        for suit in ("m", "p", "s", "z"):
            digits = groups[suit]
            if digits:
                out.append("".join(digits) + suit)
        return "".join(out)

    # ----- mutation -----------------------------------------------------

    def add(self, tile_id: int, n: int = 1) -> None:
        if not 0 <= tile_id < NUM_TILES:
            raise ValueError(f"tile id out of range: {tile_id}")
        if self.counts[tile_id] + n > 4:
            raise ValueError(f"cannot have more than 4 copies of tile id {tile_id}")
        self.counts[tile_id] += n

    def remove(self, tile_id: int, n: int = 1) -> None:
        if not 0 <= tile_id < NUM_TILES:
            raise ValueError(f"tile id out of range: {tile_id}")
        if self.counts[tile_id] < n:
            raise ValueError(f"not enough copies of tile id {tile_id} to remove")
        self.counts[tile_id] -= n

    def copy(self) -> "Hand":
        return Hand(list(self.counts))

    # ----- validation ---------------------------------------------------

    def validate(self, expect: Sequence[int] = (13, 14)) -> int:
        """Validate the hand size and return the total tile count.

        :param expect: Tuple of allowed totals (default ``(13, 14)``).
        """
        n = self.total()
        if n not in expect:
            raise ValueError(
                f"hand has {n} tiles; expected one of {expect}: {self.to_string()!r}"
            )
        for c in self.counts:
            if c < 0 or c > 4:
                raise ValueError("invalid tile count in hand")
        return n
