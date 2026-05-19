"""Tile representation for Riichi Mahjong.

Tile-id encoding (34 distinct tile types; aka-dora is treated as the
same id as the regular 5):

    0..8   ->  1m..9m   (Manzu / characters)
    9..17  ->  1p..9p   (Pinzu / dots)
    18..26 ->  1s..9s   (Souzu / bamboo)
    27..30 ->  East / South / West / North winds (1z..4z)
    31..33 ->  Haku / Hatsu / Chun dragons       (5z..7z)

The standard "mpsz" string notation is used for hand input/output, e.g.::

    "123m456p789s11122z"  ->  13 tiles: 123m + 456p + 789s + 1z 1z 1z 2z 2z
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


NUM_TILES: int = 34
"""Number of distinct tile types (aka-dora is folded into its base tile)."""

# Indices that count as terminals + honors (yaochuhai),
# used by chiitoitsu and especially kokushi shanten.
YAOCHU_IDS: tuple[int, ...] = (
    0, 8,        # 1m, 9m
    9, 17,       # 1p, 9p
    18, 26,      # 1s, 9s
    27, 28, 29, 30,   # winds
    31, 32, 33,       # dragons
)

# Aka-dora (red five) tile codes. They are *not* a fourth distinct tile id
# in the engine — for shanten / chi / pon / kan / visibility purposes they
# behave as the regular 5m / 5p / 5s. They only differ in:
#   * the asset name (Man5-Dora.svg / Pin5-Dora.svg / Sou5-Dora.svg), and
#   * counting toward the player's aka-dora total for han estimation.
#
# The "0m" / "0p" / "0s" string form is the standard mpsz convention for
# encoding a red five in a hand string. Inputs accept either form.
AKA_TILE_IDS: tuple[int, int, int] = (4, 13, 22)  # 5m / 5p / 5s
_AKA_CODE_TO_ID: dict[str, int] = {"0m": 4, "0p": 13, "0s": 22}


def is_aka_code(code: str) -> bool:
    return code.lower() in _AKA_CODE_TO_ID


def aka_image_filename_for(tile_id: int) -> str | None:
    """Return the red-variant image filename for a given tile id, or None."""
    return {4: "Man5-Dora.svg", 13: "Pin5-Dora.svg", 22: "Sou5-Dora.svg"}.get(tile_id)


_SUIT_LETTERS = ("m", "p", "s", "z")
_HONOR_NAMES = ("East", "South", "West", "North", "Haku", "Hatsu", "Chun")
_HONOR_SHORT = ("E", "S", "W", "N", "Wh", "Gr", "Rd")

# Mapping from tile-id to the SVG asset name in the FluffyStuff repository.
# Path inside the repo: Regular/<name>.svg
_IMAGE_NAMES: tuple[str, ...] = (
    # 1m..9m
    "Man1", "Man2", "Man3", "Man4", "Man5", "Man6", "Man7", "Man8", "Man9",
    # 1p..9p
    "Pin1", "Pin2", "Pin3", "Pin4", "Pin5", "Pin6", "Pin7", "Pin8", "Pin9",
    # 1s..9s
    "Sou1", "Sou2", "Sou3", "Sou4", "Sou5", "Sou6", "Sou7", "Sou8", "Sou9",
    # winds  E   S    W      N
    "Ton", "Nan", "Shaa", "Pei",
    # dragons  white  green   red
    "Haku", "Hatsu", "Chun",
)


@dataclass(frozen=True)
class Tile:
    """Lightweight, hashable representation of a single tile type."""

    tile_id: int

    def __post_init__(self) -> None:
        if not 0 <= self.tile_id < NUM_TILES:
            raise ValueError(f"tile_id out of range: {self.tile_id}")

    @property
    def suit(self) -> str:
        if self.tile_id < 9:
            return "m"
        if self.tile_id < 18:
            return "p"
        if self.tile_id < 27:
            return "s"
        return "z"

    @property
    def number(self) -> int:
        """Number 1-9 inside the suit (1-7 for honors)."""
        if self.tile_id < 27:
            return (self.tile_id % 9) + 1
        return self.tile_id - 27 + 1

    @property
    def is_honor(self) -> bool:
        return self.tile_id >= 27

    @property
    def is_terminal(self) -> bool:
        if self.is_honor:
            return False
        return self.number in (1, 9)

    @property
    def is_yaochu(self) -> bool:
        return self.is_honor or self.is_terminal

    @property
    def code(self) -> str:
        """Canonical mpsz code, e.g. '5m', '1z'."""
        return f"{self.number}{self.suit}"

    @property
    def short_name(self) -> str:
        """Human-friendly label used by the UI when image assets are absent."""
        if not self.is_honor:
            return self.code
        return _HONOR_SHORT[self.tile_id - 27]

    @property
    def long_name(self) -> str:
        if not self.is_honor:
            return self.code
        return _HONOR_NAMES[self.tile_id - 27]

    @property
    def image_filename(self) -> str:
        return _IMAGE_NAMES[self.tile_id] + ".svg"


def tile_id_from_code(code: str) -> int:
    """Parse a single tile code such as '5m' or '1z' to a tile id.

    Also accepts the red-five aliases ``0m`` / ``0p`` / ``0s`` and returns
    the regular 5m / 5p / 5s id (4 / 13 / 22). The "this is a red five"
    flag must be tracked separately by the caller.
    """
    code = code.strip().lower()
    if code in _AKA_CODE_TO_ID:
        return _AKA_CODE_TO_ID[code]
    if len(code) != 2 or not code[0].isdigit() or code[1] not in _SUIT_LETTERS:
        raise ValueError(f"invalid tile code: {code!r}")
    n = int(code[0])
    suit = code[1]
    if suit == "z":
        if not 1 <= n <= 7:
            raise ValueError(f"honor must be 1z..7z, got {code!r}")
        return 27 + (n - 1)
    if not 1 <= n <= 9:
        raise ValueError(f"numbered tile must be 1-9, got {code!r}")
    base = {"m": 0, "p": 9, "s": 18}[suit]
    return base + (n - 1)


def tile_code(tile_id: int) -> str:
    return Tile(tile_id).code


def tile_short_name(tile_id: int) -> str:
    return Tile(tile_id).short_name


def image_filename_for_tile(tile_id: int) -> str:
    return Tile(tile_id).image_filename


def parse_hand(text: str) -> List[int]:
    """Parse a compact mpsz string into a list of tile ids.

    Accepts strings such as ``"123m456p789s11122z"`` or with whitespace and
    commas. The order of suits is irrelevant; tiles before the suit letter
    all share that suit. Each character must be a digit followed eventually
    by one of m/p/s/z.
    """

    cleaned = text.replace(" ", "").replace(",", "").lower()
    if not cleaned:
        return []

    out: List[int] = []
    pending_digits: list[str] = []
    for ch in cleaned:
        if ch.isdigit():
            pending_digits.append(ch)
        elif ch in _SUIT_LETTERS:
            if not pending_digits:
                raise ValueError(
                    f"suit letter {ch!r} with no preceding digits in {text!r}"
                )
            for d in pending_digits:
                out.append(tile_id_from_code(d + ch))
            pending_digits = []
        else:
            raise ValueError(f"unexpected character {ch!r} in {text!r}")
    if pending_digits:
        raise ValueError(
            f"trailing digits without suit letter in {text!r}: {''.join(pending_digits)}"
        )
    return out


def counts_to_codes(counts: Sequence[int]) -> List[str]:
    """Expand a 34-length count vector to a sorted list of tile codes.

    Handy for displaying or serialising a hand.
    """
    if len(counts) != NUM_TILES:
        raise ValueError(f"counts must have length {NUM_TILES}, got {len(counts)}")
    out: List[str] = []
    for tid, c in enumerate(counts):
        if c < 0 or c > 4:
            raise ValueError(f"tile count for id {tid} must be in 0..4, got {c}")
        out.extend([tile_code(tid)] * c)
    return out


def counts_from_ids(tile_ids: Iterable[int]) -> List[int]:
    """Build a 34-length count vector from an iterable of tile ids."""
    counts = [0] * NUM_TILES
    for tid in tile_ids:
        if not 0 <= tid < NUM_TILES:
            raise ValueError(f"tile id out of range: {tid}")
        counts[tid] += 1
        if counts[tid] > 4:
            raise ValueError(f"more than 4 copies of tile id {tid}")
    return counts
