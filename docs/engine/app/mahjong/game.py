"""Game-state model used by Phase 2 (defense + manual game tracking).

The state is **stateless on the server** — every analysis request carries
the full game snapshot. The frontend owns the action history (for undo)
and persists state in localStorage. This keeps the Python side a pure
function: ``game_state -> analysis``.

Player ordering follows mahjong convention. ``self`` is always the user.
Opponents are ordered around the table:

    0 = self / user
    1 = shimocha (right / next in turn order)
    2 = toimen   (across)
    3 = kamicha  (left / previous in turn order)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from .tiles import NUM_TILES, Tile, parse_hand, tile_id_from_code


# Player indices.
SEAT_NAMES: tuple[str, ...] = ("self", "shimocha", "toimen", "kamicha")
SEAT_LABEL: dict[str, str] = {
    "self": "You",
    "shimocha": "Right (shimocha)",
    "toimen": "Across (toimen)",
    "kamicha": "Left (kamicha)",
}

# Honor tile-id helpers.
WIND_IDS: tuple[int, int, int, int] = (27, 28, 29, 30)  # E, S, W, N
DRAGON_IDS: tuple[int, int, int] = (31, 32, 33)


_VALID_MELD_TYPES = ("chi", "pon", "kan", "ankan")


@dataclass
class Meld:
    """A called meld owned by some player.

    For Phase 2 these are recorded for visibility (kabe / dora-after-kan)
    but the engine does not yet make call decisions of its own.

    ``aka_count`` records how many of this meld's tiles are red fives.
    The engine treats them as identical to regular 5s for shanten and
    visibility; the field only feeds han/dora valuation.
    """

    type: str
    tiles: List[int]
    called_from: Optional[int] = None  # which seat the call took the tile from
    aka_count: int = 0

    def __post_init__(self) -> None:
        if self.type not in _VALID_MELD_TYPES:
            raise ValueError(f"unknown meld type: {self.type!r}")
        if self.type in ("chi", "pon"):
            if len(self.tiles) != 3:
                raise ValueError(f"{self.type} meld must have 3 tiles")
        elif self.type in ("kan", "ankan"):
            if len(self.tiles) != 4:
                raise ValueError(f"{self.type} meld must have 4 tiles")
        for tid in self.tiles:
            if not 0 <= tid < NUM_TILES:
                raise ValueError(f"invalid tile id in meld: {tid}")
        if self.aka_count < 0:
            raise ValueError("aka_count must be >= 0")

    @property
    def is_concealed(self) -> bool:
        return self.type == "ankan"


@dataclass
class PlayerState:
    """Per-player public state visible to all participants."""

    discards: List[int] = field(default_factory=list)
    melds: List[Meld] = field(default_factory=list)
    riichi: bool = False
    riichi_discard_index: Optional[int] = None
    """Index into ``discards`` of the discard that *declared* riichi.
    All discards at or after this index are post-riichi (genbutsu sources)."""

    def post_riichi_discards(self) -> List[int]:
        if not self.riichi or self.riichi_discard_index is None:
            return []
        return list(self.discards[self.riichi_discard_index :])


@dataclass
class GameState:
    """A complete snapshot of the manually-tracked hand.

    Everything the AI needs to give efficiency + defense advice fits here.
    """

    # ----- table-level -------------------------------------------------
    round_wind: int = 27           # tile-id of the round wind (1z=East default)
    seat_wind: int = 27            # tile-id of the user's seat wind
    honba: int = 0
    riichi_sticks: int = 0
    dora_indicators: List[int] = field(default_factory=list)
    turn_number: int = 0           # 1-indexed turn count for the user; 0 = pre-deal

    # ----- user --------------------------------------------------------
    hand: List[int] = field(default_factory=list)
    """The user's *closed* hand including the most recent draw if any.
    Length: 13 (between turns) or 14 (after drawing, before discarding).
    Ankan meld tiles are tracked in ``melds`` instead, not in ``hand``."""

    drawn_tile: Optional[int] = None
    """Hint to the UI / explainer about which tile is the latest draw.
    Must be present in ``hand`` (i.e. it is part of the 14-tile state).
    Optional; ``None`` is fine for a 14-tile post-draw state."""

    aka_in_hand: int = 0
    """Number of red fives among the user's concealed tiles. Combined with
    each meld's ``aka_count`` to compute the user's total aka-dora."""

    user: PlayerState = field(default_factory=PlayerState)
    opponents: List[PlayerState] = field(
        default_factory=lambda: [PlayerState(), PlayerState(), PlayerState()]
    )

    # ----- validation --------------------------------------------------

    def __post_init__(self) -> None:
        if self.round_wind not in WIND_IDS:
            raise ValueError(f"round_wind must be a wind tile id (27..30), got {self.round_wind}")
        if self.seat_wind not in WIND_IDS:
            raise ValueError(f"seat_wind must be a wind tile id (27..30), got {self.seat_wind}")
        if self.honba < 0:
            raise ValueError("honba must be >= 0")
        if self.riichi_sticks < 0:
            raise ValueError("riichi_sticks must be >= 0")
        if len(self.opponents) != 3:
            raise ValueError("there must be exactly 3 opponents")
        if self.aka_in_hand < 0:
            raise ValueError("aka_in_hand must be >= 0")
        for tid in self.hand + self.dora_indicators:
            if not 0 <= tid < NUM_TILES:
                raise ValueError(f"tile id out of range: {tid}")

    # ----- accessors ---------------------------------------------------

    def player(self, seat_index: int) -> PlayerState:
        if seat_index == 0:
            return self.user
        if 1 <= seat_index <= 3:
            return self.opponents[seat_index - 1]
        raise IndexError(f"seat index out of range: {seat_index}")

    def all_players(self) -> List[PlayerState]:
        return [self.user] + list(self.opponents)

    def hand_counts(self) -> List[int]:
        counts = [0] * NUM_TILES
        for tid in self.hand:
            counts[tid] += 1
        return counts

    def hand_size(self) -> int:
        return len(self.hand)

    def is_post_draw(self) -> bool:
        return len(self.hand) == 14

    # ----- factories ---------------------------------------------------

    @classmethod
    def from_hand(
        cls,
        hand: Iterable[int] | str,
        round_wind: int | str = "1z",
        seat_wind: int | str = "1z",
        dora_indicators: Iterable[int] | str | None = None,
        honba: int = 0,
    ) -> "GameState":
        """Convenience constructor used by tests and the simple API."""
        if isinstance(hand, str):
            hand_ids = parse_hand(hand)
        else:
            hand_ids = list(hand)
        if isinstance(round_wind, str):
            round_wind = tile_id_from_code(round_wind)
        if isinstance(seat_wind, str):
            seat_wind = tile_id_from_code(seat_wind)
        if dora_indicators is None:
            dora_ids: List[int] = []
        elif isinstance(dora_indicators, str):
            dora_ids = parse_hand(dora_indicators)
        else:
            dora_ids = list(dora_indicators)
        return cls(
            round_wind=round_wind,
            seat_wind=seat_wind,
            honba=honba,
            dora_indicators=dora_ids,
            hand=hand_ids,
        )


# ---------------------------------------------------------------------------
# Dora helpers
# ---------------------------------------------------------------------------


def dora_tile_for(indicator_id: int) -> int:
    """Return the tile that *is* dora given the indicator tile.

    Number suits cycle 1->2->...->9->1.
    Winds cycle E->S->W->N->E.
    Dragons cycle Haku->Hatsu->Chun->Haku.
    """
    if indicator_id < 27:
        suit_base = (indicator_id // 9) * 9
        n = indicator_id - suit_base
        return suit_base + (n + 1) % 9
    if 27 <= indicator_id <= 30:  # winds
        offset = indicator_id - 27
        return 27 + (offset + 1) % 4
    # dragons 31..33
    offset = indicator_id - 31
    return 31 + (offset + 1) % 3


def dora_tiles(indicators: Iterable[int]) -> List[int]:
    return [dora_tile_for(i) for i in indicators]


def total_user_aka(state: "GameState") -> int:
    """Aka-dora the user owns (concealed hand + every owned meld)."""
    return state.aka_in_hand + sum(m.aka_count for m in state.user.melds)


def visible_aka_in_player(player: PlayerState) -> int:
    """Aka-dora visible in a player's *open* melds (and ankan, since it's
    placed face-up after the kan reveal)."""
    return sum(m.aka_count for m in player.melds)
