"""Global tile-pool sanity validation.

A real game only has 4 of every tile (3 normal 5 + 1 red 5 in each
five-tile suit). The frontend can desync if a meld is recorded twice or
a discard lingers in two places at once; this module reports any such
impossibilities so the API can fail fast instead of producing nonsense
analysis from a corrupt :class:`GameState`.
"""

from __future__ import annotations

from typing import List

from .game import GameState
from .tiles import AKA_TILE_IDS, NUM_TILES, tile_code


def count_visible_tiles(state: GameState) -> List[int]:
    """Return a 34-length count vector totalling every tile that the
    engine "knows about" in this state.

    Sources:

    * user concealed hand
    * dora indicators (visible, from the dead wall)
    * every player's discard river
    * every player's open + concealed melds (chi / pon / kan / ankan)

    The latest discard is **not** counted separately — it is already part
    of the discarder's discard river by convention.
    """
    counts = [0] * NUM_TILES
    for tid in state.hand:
        if 0 <= tid < NUM_TILES:
            counts[tid] += 1
    for tid in state.dora_indicators:
        if 0 <= tid < NUM_TILES:
            counts[tid] += 1
    for player in state.all_players():
        for tid in player.discards:
            if 0 <= tid < NUM_TILES:
                counts[tid] += 1
        for meld in player.melds:
            for tid in meld.tiles:
                if 0 <= tid < NUM_TILES:
                    counts[tid] += 1
    return counts


def count_visible_aka(state: GameState) -> dict:
    """Return red-five count per suit-base (5m=4, 5p=13, 5s=22).

    User's concealed-hand reds are tracked in :attr:`GameState.aka_in_hand`
    and not split per suit, so they are added to a special ``"hand"``
    bucket; per-suit limits are still enforced via the visible-meld counts.
    """
    out = {tid: 0 for tid in AKA_TILE_IDS}
    for player in state.all_players():
        for meld in player.melds:
            if meld.aka_count > 0:
                for tid in meld.tiles:
                    if tid in AKA_TILE_IDS:
                        out[tid] += meld.aka_count
                        break
    return out


def validate_tile_pool(state: GameState) -> List[str]:
    """Run full pool-consistency checks; return human-readable error
    messages, or an empty list when the state is consistent.

    Checks:

    * No tile id appears more than 4 times across all visible sources.
    * No suit has more than 1 red five visible in melds.
    * The user's ``aka_in_hand`` cannot exceed the total number of 5m+5p+5s
      in their concealed hand and cannot exceed 3 (one red per suit).
    """
    errors: List[str] = []

    counts = count_visible_tiles(state)
    for tid, c in enumerate(counts):
        if c > 4:
            errors.append(
                f"tile {tile_code(tid)}: {c} copies visible (max 4)."
            )

    aka_counts = count_visible_aka(state)
    for tid, c in aka_counts.items():
        if c > 1:
            errors.append(
                f"red 5{_suit_letter(tid)}: {c} red copies in open melds (max 1)."
            )

    user_5_total = sum(state.hand_counts()[tid] for tid in AKA_TILE_IDS)
    if state.aka_in_hand < 0:
        errors.append("aka_in_hand must be >= 0.")
    elif state.aka_in_hand > user_5_total:
        errors.append(
            f"aka_in_hand ({state.aka_in_hand}) exceeds 5s in hand ({user_5_total})."
        )
    elif state.aka_in_hand > 3:
        errors.append(
            f"aka_in_hand ({state.aka_in_hand}) exceeds 3 (one red per suit max)."
        )

    return errors


def _suit_letter(aka_id: int) -> str:
    return {4: "m", 13: "p", 22: "s"}.get(aka_id, "?")
