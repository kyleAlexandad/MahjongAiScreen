"""Strict call-legality checks for the **user**.

These are pure functions over :class:`GameState` that mirror the
client-side legality logic in ``frontend/static/app.js``. Both layers
must agree:

* The frontend uses them to **disable** illegal Pon/Kan/Chi drop zones
  before the user can even drop on them.
* The backend uses them in :mod:`calls` and the API to **reject**
  payloads that try to record an impossible meld (UI bypass / bug).

For *opponent* calls we cannot strictly validate because their hidden
hand is unknown — those are tracked manually with relaxed validation
(see :mod:`validation` for the global tile-pool sanity check).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .game import GameState
from .tiles import NUM_TILES
from .visibility import visible_counts


# ---------------------------------------------------------------------------
# Pon / Kan
# ---------------------------------------------------------------------------


def can_user_pon(state: GameState, discarded_tile: int) -> bool:
    """User can pon iff they have **at least 2** copies of the discarded
    tile in the concealed hand.

    Red fives and normal fives share the same base tile id (4/13/22), so
    "red 5m + normal 5m" already satisfies the count check.
    """
    if not 0 <= discarded_tile < NUM_TILES:
        return False
    counts = state.hand_counts()
    return counts[discarded_tile] >= 2


def can_user_open_kan(state: GameState, discarded_tile: int) -> bool:
    """User can open-kan (daiminkan) iff they have **at least 3** copies
    of the discarded tile in the concealed hand."""
    if not 0 <= discarded_tile < NUM_TILES:
        return False
    counts = state.hand_counts()
    return counts[discarded_tile] >= 3


def user_ankan_candidates(state: GameState) -> List[int]:
    """Return tile ids the user can ankan (concealed kan) on — i.e. tiles
    they hold 4 copies of in the closed hand."""
    counts = state.hand_counts()
    return [tid for tid in range(NUM_TILES) if counts[tid] >= 4]


def can_user_ankan(state: GameState, tile_id: int) -> bool:
    """User can ankan a specific tile iff they hold 4 copies of it."""
    if not 0 <= tile_id < NUM_TILES:
        return False
    counts = state.hand_counts()
    return counts[tile_id] >= 4


# ---------------------------------------------------------------------------
# Chi
# ---------------------------------------------------------------------------


def get_legal_chi_options(
    state: GameState,
    discarded_tile: int,
    discarder_seat: int,
    caller_seat: int = 0,
) -> List[Tuple[int, int]]:
    """Return the [a, b] consumed-tile pairs that form **legal** chi shapes
    on ``discarded_tile``.

    Constraints (Riichi rules):

    * Honors cannot be used in chi.
    * Chi is only legal off the seat immediately to the caller's left
      (kamicha, ``(caller_seat + 3) % 4``).
    * The two consumed tiles must both be present in the caller's hand
      (red fives count as their base 5).

    For *opponent* callers the hand contents are unknown, so we still
    enforce the geometric constraints (suit / seat) but cannot enforce
    the hand-count check; in that case we return all geometrically legal
    pairs and the caller's UI must surface the result with a "manual
    override" warning.
    """
    if not 0 <= discarded_tile < NUM_TILES:
        return []
    if discarded_tile >= 27:  # honors: chi is impossible
        return []
    callers_kamicha = (caller_seat + 3) % 4
    if discarder_seat != callers_kamicha:
        return []

    suit_base = (discarded_tile // 9) * 9
    n = (discarded_tile % 9) + 1  # 1..9 inside the suit

    geom_pairs: List[Tuple[int, int]] = []
    if n >= 3:  # x-2, x-1, x
        geom_pairs.append((discarded_tile - 2, discarded_tile - 1))
    if 2 <= n <= 8:  # x-1, x, x+1
        geom_pairs.append((discarded_tile - 1, discarded_tile + 1))
    if n <= 7:  # x, x+1, x+2
        geom_pairs.append((discarded_tile + 1, discarded_tile + 2))
    # All pairs must stay within the same suit (sanity).
    geom_pairs = [
        (a, b) for (a, b) in geom_pairs
        if suit_base <= a < suit_base + 9 and suit_base <= b < suit_base + 9
    ]

    # For the user (caller_seat == 0) require both tiles to be present in
    # the closed hand. For opponents we can't check, so accept the geometric
    # set and let the caller mark them as "manual".
    if caller_seat != 0:
        return geom_pairs

    counts = state.hand_counts()
    legal: List[Tuple[int, int]] = []
    for a, b in geom_pairs:
        if a == b:
            if counts[a] < 2:
                continue
        else:
            if counts[a] < 1 or counts[b] < 1:
                continue
        legal.append((a, b))
    return legal


def is_chi_seat_legal(caller_seat: int, discarder_seat: int) -> bool:
    """Pure seat-position check; useful when we want to surface a generic
    "can't chi from this seat" message before computing shapes."""
    if not 0 <= caller_seat <= 3 or not 0 <= discarder_seat <= 3:
        return False
    return discarder_seat == (caller_seat + 3) % 4


# ---------------------------------------------------------------------------
# Tile-pool feasibility (works for opponents whose hand is hidden)
# ---------------------------------------------------------------------------
#
# Strict hand-count checks (above) only work for the user, whose concealed
# hand we know. For an opponent we can't see their hand, but we *can* see
# everything else on the table, so we can still reject calls that are
# physically impossible: an opponent can never form a meld whose hidden
# tiles don't exist anymore.
#
#   pon  -> the opponent must hold 2 hidden copies of the called tile
#   kan  -> the opponent must hold 3 hidden copies (daiminkan)
#   chi  -> the opponent must hold 1 hidden copy of EACH of the two run tiles
#
# A "hidden copy" is one that is not already visible anywhere the engine can
# see (the user's hand, dora indicators, every discard pile, every meld).
# These helpers are meant to be called *before* the meld is recorded, while
# the called discard is still sitting in the discarder's river — exactly the
# point where the frontend decides whether to allow the drop / button.


def remaining_unseen(state: GameState) -> List[int]:
    """Copies of each tile id not visible anywhere on the table.

    ``4 - visible`` where ``visible`` counts the user's hand, dora
    indicators, every discard pile and every meld. The called discard is
    part of a discard pile at call time, so it is treated as *visible* (one
    of the four copies); the meld's remaining tiles must come from the
    opponent's hidden hand and therefore from this unseen pool.
    """
    return [max(0, 4 - v) for v in visible_counts(state)]


def opponent_call_feasible(
    state: GameState,
    call_type: str,
    tile_id: int,
    run_pair: Optional[Tuple[int, int]] = None,
) -> bool:
    """Whether an opponent could physically have made ``call_type`` on
    ``tile_id`` given everything currently visible.

    Returns ``True`` for shapes we cannot constrain (unknown ``call_type``)
    so this never blocks something it isn't sure about — it only rejects the
    provably impossible.
    """
    if not 0 <= tile_id < NUM_TILES:
        return False
    unseen = remaining_unseen(state)
    if call_type == "pon":
        return unseen[tile_id] >= 2
    if call_type == "kan":  # daiminkan: 3 hidden + the discard
        return unseen[tile_id] >= 3
    if call_type == "chi":
        if run_pair is None:
            return True
        a, b = run_pair
        if not (0 <= a < NUM_TILES and 0 <= b < NUM_TILES):
            return False
        if a == b:  # never a valid run shape
            return False
        return unseen[a] >= 1 and unseen[b] >= 1
    return True
