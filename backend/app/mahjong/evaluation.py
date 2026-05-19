"""Expected-value play model — the "strong classical AI" layer.

The Phase-1/2 recommender ranked discards with a crude
``0.7*efficiency + 0.3*safety`` blend. That ignores *how wide the hand
becomes two steps out*, *how much the hand is worth*, and *how much a
deal-in actually costs*. This module replaces that with a principled
expected-value estimate:

    EV(discard) = P(win | resulting shape) * value(our hand)
                  - Σ_opponent  P(deal in with this tile) * value(opponent)

Each term is a calibrated heuristic (no neural net, no external data, runs
offline in milliseconds), but together they behave like a real player:

* **Two-step weighted acceptance** (``ukeire²``): a discard is judged by
  the *quality of the tenpai it advances into*, not just the count of
  tiles that drop shanten by one.
* **Win probability**: monotone in shanten, acceptance width and draws
  left — a tenpai with a wide wait early is worth far more than a narrow
  one in the endgame.
* **Hand value**: real han→points scoring (mangan caps, dealer ×1.5),
  fed by the existing han estimator, with a riichi/closed bonus.
* **Push / fold**: against a riichi the deal-in cost term is real points,
  so genuinely dangerous tiles are folded and safe tiles are pushed — the
  same EV formula collapses to pure efficiency when nobody threatens.

The numbers are deliberately documented as heuristic: they give strong,
explainable beginner-to-intermediate guidance, not Tenhou-stable win
rates. See README "Notes on correctness".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .game import GameState
from .shanten import calculate_shanten
from .tiles import NUM_TILES
from .ukeire import calculate_ukeire


# A hand sees ~17-18 draws over an East/South round before exhaustive draw.
DRAWS_PER_HAND = 18


# ---------------------------------------------------------------------------
# 1. Two-step weighted acceptance (ukeire²)
# ---------------------------------------------------------------------------


def weighted_acceptance(
    counts13: List[int],
    remaining: Optional[Sequence[int]],
    open_melds_count: int,
    shanten: int,
) -> Tuple[int, float]:
    """Return ``(ukeire_count, quality)`` for a 13-tile shape.

    ``ukeire_count`` is the classic one-step acceptance (sum of remaining
    copies of every tile that lowers shanten). ``quality`` is the
    two-step mass: for each accepted tile, how wide the *best* resulting
    shape's own acceptance is, weighted by how many copies of that tile
    can still be drawn. A shape that advances into a fat tenpai scores
    much higher than one that advances into a narrow tanki.

    Cost is bounded by the shanten cache; we only expand the second step
    for shapes that are realistically close (shanten ≤ 3).
    """
    ukeire = calculate_ukeire(
        counts13,
        current_shanten=shanten,
        remaining=remaining,
        open_melds_count=open_melds_count,
    )
    uke_count = sum(ukeire.values())
    if shanten < 0 or not ukeire or shanten > 3:
        # Winning, dead, or too far out for a meaningful 2-step expansion.
        return uke_count, float(uke_count)

    target = shanten - 1
    quality = 0.0
    for tid, copies in ukeire.items():
        counts13[tid] += 1
        best2 = 0
        for d in range(NUM_TILES):
            if counts13[d] == 0:
                continue
            counts13[d] -= 1
            sh2 = calculate_shanten(counts13, open_melds_count)
            if sh2 <= target:
                u2 = calculate_ukeire(
                    counts13,
                    current_shanten=sh2,
                    remaining=remaining,
                    open_melds_count=open_melds_count,
                )
                c2 = sum(u2.values())
                if c2 > best2:
                    best2 = c2
            counts13[d] += 1
        counts13[tid] -= 1
        quality += copies * best2
    return uke_count, quality


# ---------------------------------------------------------------------------
# 2. Win probability
# ---------------------------------------------------------------------------


# Rough hand-win rates by shanten for a closed hand drawing freely from
# mid-game (community-known ballparks; not exact Tenhou figures).
_BASE_WIN_P = {0: 0.50, 1: 0.225, 2: 0.095, 3: 0.042, 4: 0.018}


def draws_left(state: GameState) -> int:
    """Approximate user draws remaining this hand."""
    return max(1, DRAWS_PER_HAND - max(0, state.turn_number))


def win_probability(
    shanten: int,
    uke_count: int,
    quality: float,
    draws: int,
    *,
    is_closed: bool = True,
) -> float:
    """Calibrated P(this hand eventually wins) in [0, 0.95].

    Monotone in: lower shanten, wider acceptance/quality, more draws left.
    """
    if shanten < 0:
        return 1.0
    base = _BASE_WIN_P.get(shanten, 0.007)
    if shanten == 0:
        # Tenpai: wider wait → meaningfully better; narrow tanki → worse.
        acc = min(1.5, 0.45 + uke_count / 11.0)
    else:
        # Use the 2-step mass; sqrt keeps the curve gentle.
        acc = min(1.6, 0.55 + (quality ** 0.5) / 13.0)
    draw_factor = min(1.0, draws / 12.0)
    # Even with few draws a tenpai still wins sometimes (ron); never zero it.
    p = base * acc * (0.35 + 0.65 * draw_factor)
    if not is_closed:
        # Open hands give up menzen tsumo / a closed wait edge — small tax.
        p *= 0.92
    return max(0.0, min(0.95, p))


# ---------------------------------------------------------------------------
# 3. Hand value (han → points)
# ---------------------------------------------------------------------------


# Approx non-dealer ron value by han (averaged fu; mangan-capped at 5).
_NONDEALER_POINTS = {
    0: 0, 1: 1000, 2: 2400, 3: 4800, 4: 7700,
    5: 8000, 6: 12000, 7: 12000, 8: 16000, 9: 16000,
    10: 16000, 11: 24000, 12: 24000,
}


def points_for_han(han: int, dealer: bool) -> int:
    """Approximate point value of a winning hand of ``han`` han.

    Dealer hands are worth ~1.5×. 13+ han is treated as yakuman.
    """
    if han <= 0:
        return 0
    if han >= 13:
        base = 32000
    else:
        base = _NONDEALER_POINTS.get(han, 8000)
    return int(round(base * (1.5 if dealer else 1.0)))


def _is_dealer(state: GameState, seat: int) -> bool:
    """User (seat 0) is dealer when their seat wind is the round wind
    (East seat in the East round). Opponents shift one wind per seat."""
    if seat == 0:
        return state.seat_wind == state.round_wind
    winds = [27, 28, 29, 30]
    base = winds.index(state.seat_wind)
    opp_wind = winds[(base + seat) % 4]
    return opp_wind == state.round_wind


def estimate_self_value(
    state: GameState,
    han_estimates: List[dict],
    shanten: int,
    *,
    is_closed: bool,
) -> int:
    """Expected points if the user completes this hand.

    Uses the existing han estimate and adds a riichi bonus when the hand
    is closed and close enough to declare it (riichi itself plus an
    averaged ippatsu / ura-dora expectation ≈ +1.5 han, floored to +1).
    """
    he = han_estimates[0] if han_estimates else {"han": 0}
    han = int(he.get("han", 0))
    if is_closed and not state.user.riichi and shanten <= 1:
        han += 1  # will declare riichi; conservative (ignores ippatsu/ura)
    # You can't win valueless; assume at least a 1-han path exists.
    han = max(han, 1)
    return points_for_han(han, _is_dealer(state, 0))


def estimate_opponent_value(
    state: GameState,
    han_estimates: List[dict],
    seat: int,
) -> int:
    """Expected points the user loses if they deal into ``seat``.

    A declared riichi averages ~3-4 han once ura-dora / dora are folded
    in; an un-revealed opponent is floored lower.
    """
    he = han_estimates[seat] if seat < len(han_estimates) else {"han": 0}
    han = int(he.get("han", 0))
    if state.player(seat).riichi:
        han = max(han, 4)
    else:
        han = max(han, 2)
    return points_for_han(han, _is_dealer(state, seat))


# ---------------------------------------------------------------------------
# 4. Deal-in probability + expected value
# ---------------------------------------------------------------------------


def dealin_probability(danger_score: int, *, opp_riichi: bool) -> float:
    """Map a 0..100 heuristic danger score to a deal-in probability.

    Danger 0 (genbutsu) → 0. Danger 100 vs a riichi ≈ 20% to actually
    deal in if pushed now; vs a non-declared opponent the realised rate
    is much lower.
    """
    k = 0.20 if opp_riichi else 0.05
    return max(0.0, min(1.0, (danger_score / 100.0) * k))


@dataclass
class DiscardEV:
    win_p: float
    self_value: int
    dealin_cost: float
    ev: float

    def to_dict(self) -> dict:
        return {
            "win_p": round(self.win_p, 4),
            "self_value": self.self_value,
            "dealin_cost": round(self.dealin_cost, 1),
            "ev": round(self.ev, 1),
        }


def discard_expected_value(
    win_p: float,
    self_value: int,
    per_opponent: Sequence[Tuple[int, int, bool]],
) -> DiscardEV:
    """``per_opponent`` is a list of ``(danger_score, opp_value,
    opp_riichi)`` tuples — one per opponent seat."""
    cost = 0.0
    for danger_score, opp_value, opp_riichi in per_opponent:
        cost += dealin_probability(danger_score, opp_riichi=opp_riichi) * opp_value
    ev = win_p * self_value - cost
    return DiscardEV(win_p=win_p, self_value=self_value, dealin_cost=cost, ev=ev)
