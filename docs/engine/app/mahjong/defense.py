"""Defensive analysis: genbutsu / suji / kabe / per-tile danger scores.

The output is a heuristic 0..100 danger value plus human-readable reasons,
intended for **beginner-friendly explanations**. It is *not* a precise win
probability. Phase 2 deliberately ignores:

* yaku / hand value estimation
* push-vs-fold cost-benefit modelling
* call / riichi *decisions*

Those belong to Stage 3 in the prompt.

Scale
-----
* 0       - genbutsu against every threatening opponent (perfectly safe)
* 1..15   - very safe (suji + kabe + honors with multiple copies)
* 16..35  - mildly safe
* 36..60  - neutral / unknown
* 61..85  - dangerous (middle tiles vs riichi)
* 86..100 - very dangerous (no protection vs riichi)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from .game import DRAGON_IDS, GameState, PlayerState, SEAT_LABEL, SEAT_NAMES, WIND_IDS
from .tiles import NUM_TILES, Tile


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class OpponentDanger:
    seat: int
    seat_name: str
    seat_label: str
    riichi: bool
    score: int
    label: str
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "seat": self.seat,
            "seat_name": self.seat_name,
            "seat_label": self.seat_label,
            "riichi": self.riichi,
            "score": self.score,
            "label": self.label,
            "reasons": list(self.reasons),
        }


@dataclass
class TileDanger:
    tile_id: int
    score: int
    label: str
    summary: str
    per_opponent: List[OpponentDanger] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "score": self.score,
            "label": self.label,
            "summary": self.summary,
            "per_opponent": [o.to_dict() for o in self.per_opponent],
        }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Map: tile-suit-number -> list of suji partner numbers in same suit.
_SUJI_PARTNERS: dict[int, tuple[int, ...]] = {
    1: (4,),
    2: (5,),
    3: (6,),
    4: (1, 7),
    5: (2, 8),
    6: (3, 9),
    7: (4,),
    8: (5,),
    9: (6,),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assess_tile_danger(
    tile_id: int,
    state: GameState,
    visible: Sequence[int],
) -> TileDanger:
    """Compute the danger of *discarding* ``tile_id`` given the game state."""
    if not 0 <= tile_id < NUM_TILES:
        raise ValueError(f"tile id out of range: {tile_id}")

    per_opp: list[OpponentDanger] = []
    post_riichi_pool = _post_riichi_safe_pool(state)

    for seat in (1, 2, 3):
        opp = state.player(seat)
        per_opp.append(
            _assess_vs_opponent(tile_id, state, seat, opp, visible, post_riichi_pool[seat])
        )

    worst = max(per_opp, key=lambda p: p.score)
    summary = _summarise(tile_id, worst, per_opp)
    return TileDanger(
        tile_id=tile_id,
        score=worst.score,
        label=worst.label,
        summary=summary,
        per_opponent=per_opp,
    )


def assess_all_discards(
    candidate_ids: Sequence[int],
    state: GameState,
    visible: Sequence[int],
) -> dict[int, TileDanger]:
    """Convenience: assess danger for many candidate tiles in one call."""
    return {tid: assess_tile_danger(tid, state, visible) for tid in set(candidate_ids)}


# ---------------------------------------------------------------------------
# Per-opponent scoring
# ---------------------------------------------------------------------------


def _assess_vs_opponent(
    tile_id: int,
    state: GameState,
    seat: int,
    opp: PlayerState,
    visible: Sequence[int],
    post_riichi_safe: set[int],
) -> OpponentDanger:
    seat_name = SEAT_NAMES[seat]
    seat_label = SEAT_LABEL[seat_name]
    reasons: list[str] = []

    # 1. Hard-safe via opponent's own discard pile (furiten).
    if tile_id in opp.discards:
        return OpponentDanger(
            seat=seat,
            seat_name=seat_name,
            seat_label=seat_label,
            riichi=opp.riichi,
            score=0,
            label="genbutsu",
            reasons=[f"{seat_label} discarded this tile earlier (genbutsu)"],
        )

    # 2. Hard-safe vs a riichi opponent via post-riichi public discards.
    if opp.riichi and tile_id in post_riichi_safe:
        return OpponentDanger(
            seat=seat,
            seat_name=seat_name,
            seat_label=seat_label,
            riichi=True,
            score=0,
            label="genbutsu",
            reasons=[f"Discarded by someone after {seat_label}'s riichi (genbutsu)"],
        )

    # No hard genbutsu — produce a heuristic score.
    base = 60 if opp.riichi else 25
    if opp.riichi:
        reasons.append(f"{seat_label} declared riichi — push tiles carefully")

    tile = Tile(tile_id)
    visible_copies = visible[tile_id]

    if tile.is_honor:
        return _assess_honor(
            tile, seat, seat_name, seat_label, opp, visible_copies, base, reasons, state
        )
    return _assess_numbered(
        tile, seat, seat_name, seat_label, opp, visible, base, reasons
    )


def _assess_honor(
    tile: Tile,
    seat: int,
    seat_name: str,
    seat_label: str,
    opp: PlayerState,
    visible_copies: int,
    base: int,
    reasons: list[str],
    state: GameState,
) -> OpponentDanger:
    if visible_copies >= 3:
        base = min(base, 5)
        reasons.append("3 copies already visible — only 1 left, very limited risk")
    elif visible_copies >= 2:
        base = min(base, 18)
        reasons.append("2 copies visible — only shanpon / tanki risk")
    else:
        # Wind / dragon distinctions.
        if tile.tile_id in DRAGON_IDS:
            reasons.append("Dragon tile — yakuhai pair risk")
            base += 5
        else:
            # Wind: weight by whether it's the round or seat wind.
            if tile.tile_id == state.round_wind:
                reasons.append("Round wind — yakuhai pair risk")
                base += 5
            elif tile.tile_id == state.seat_wind:
                reasons.append("Your seat wind (still risky for opponents who share it)")
            else:
                reasons.append("Off-wind honor — usually low risk if no copies seen")
                base -= 10

    base = _clamp(base)
    return OpponentDanger(
        seat=seat,
        seat_name=seat_name,
        seat_label=seat_label,
        riichi=opp.riichi,
        score=base,
        label=_label_from_score(base),
        reasons=reasons,
    )


def _assess_numbered(
    tile: Tile,
    seat: int,
    seat_name: str,
    seat_label: str,
    opp: PlayerState,
    visible: Sequence[int],
    base: int,
    reasons: list[str],
) -> OpponentDanger:
    n = tile.number
    suit = tile.suit

    # Edge vs middle.
    if n in (1, 9):
        base -= 10
        reasons.append("Terminal tile — fewer wait shapes")
    elif n in (4, 5, 6):
        base += 8
        reasons.append("Middle tile — many possible ryanmen / kanchan waits")

    # Suji.
    suji_partners = _SUJI_PARTNERS[n]
    matched = [p for p in suji_partners if _has_in_suit(opp.discards, suit, p)]
    if len(matched) == len(suji_partners) and suji_partners:
        # Full suji (covers every ryanmen path into this tile from this opp).
        base -= 22
        if len(suji_partners) == 2:
            reasons.append(
                f"Full suji vs {seat_label} ({matched[0]}{suit}/{matched[1]}{suit} both discarded)"
            )
        else:
            reasons.append(
                f"Suji vs {seat_label} ({matched[0]}{suit} discarded — covers the only ryanmen path)"
            )
    elif matched:
        base -= 10
        reasons.append(f"Half suji vs {seat_label} ({matched[0]}{suit} discarded)")

    # Kabe — count visible copies of nearby tiles.
    kabe_reason = _kabe_reason(tile, visible)
    if kabe_reason is not None:
        base -= 12
        reasons.append(kabe_reason)

    # Plenty visible already?
    if visible[tile.tile_id] >= 3:
        base = min(base, 8)
        reasons.append("3 of these are already visible — pair / tanki risk only")
    elif visible[tile.tile_id] >= 2:
        base -= 5
        reasons.append("2 already visible — limits shanpon waits")

    base = _clamp(base)
    return OpponentDanger(
        seat=seat,
        seat_name=seat_name,
        seat_label=seat_label,
        riichi=opp.riichi,
        score=base,
        label=_label_from_score(base),
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_riichi_safe_pool(state: GameState) -> dict[int, set[int]]:
    """For each opponent seat, the set of tile ids confirmed safe via
    post-riichi public discards.

    A tile is post-riichi-safe vs opponent S if it has been discarded by any
    player **after** S declared riichi. (S would have called ron otherwise.)
    """
    pool: dict[int, set[int]] = {1: set(), 2: set(), 3: set()}
    for target_seat in (1, 2, 3):
        target = state.player(target_seat)
        if not target.riichi or target.riichi_discard_index is None:
            continue
        # Walk every player's discard pile and admit tiles that were thrown
        # *after* the target's declaring discard. We approximate ordering by
        # pile length — a finer turn-by-turn timeline can come in a later
        # phase if needed.
        for seat_idx, player in enumerate(state.all_players()):
            for discard_idx, tid in enumerate(player.discards):
                if seat_idx == target_seat and discard_idx >= target.riichi_discard_index:
                    pool[target_seat].add(tid)
                elif seat_idx != target_seat:
                    # Without a full timeline assume any other-player discard
                    # whose pile-index is at least as deep as the target's
                    # riichi index is post-riichi.
                    if discard_idx >= target.riichi_discard_index:
                        pool[target_seat].add(tid)
    return pool


def _has_in_suit(discards: Sequence[int], suit: str, number: int) -> bool:
    suit_base = {"m": 0, "p": 9, "s": 18}.get(suit)
    if suit_base is None:
        return False
    target = suit_base + number - 1
    return target in discards


def _kabe_reason(tile: Tile, visible: Sequence[int]) -> str | None:
    """If a wall (4 visible) of a neighbouring tile makes a ryanmen path
    impossible, return a beginner-friendly explanation. Otherwise ``None``."""
    n = tile.number
    suit = tile.suit
    suit_base = {"m": 0, "p": 9, "s": 18}.get(suit)
    if suit_base is None:
        return None

    # If 4 of this tile itself are visible, no ryanmen wait can target it.
    if visible[tile.tile_id] >= 4:
        return f"4 copies of {n}{suit} visible — kabe (no opponent can wait on it)"

    # Tiles N-2 and N+2 act as kabe for ryanmen ending in our number.
    # If 4 of N+2 are visible: the ryanmen (N+1, N+2) is impossible -> the
    # wait via that ryanmen onto our tile is impossible.
    candidates = []
    if 1 <= n + 2 <= 9 and visible[suit_base + (n + 2) - 1] >= 4:
        candidates.append(f"{n+2}{suit}")
    if 1 <= n - 2 <= 9 and visible[suit_base + (n - 2) - 1] >= 4:
        candidates.append(f"{n-2}{suit}")
    if candidates:
        return f"Kabe nearby ({', '.join(candidates)} fully visible) — one ryanmen path is impossible"
    return None


def _summarise(tile_id: int, worst: OpponentDanger, per_opp: List[OpponentDanger]) -> str:
    threats = [p for p in per_opp if p.riichi]
    if worst.score == 0:
        if threats:
            riichi_seats = ", ".join(p.seat_label for p in threats)
            if all(p.score == 0 for p in threats):
                return f"Safe vs every riichi opponent ({riichi_seats})."
        return f"Safe (genbutsu vs {worst.seat_label})."
    if worst.label in ("very-safe", "safe"):
        return f"Likely safe — worst case is {worst.label} vs {worst.seat_label}."
    if worst.label == "neutral":
        return f"No strong information — neutral risk vs {worst.seat_label}."
    if worst.label == "warning":
        return f"Caution: medium risk vs {worst.seat_label}."
    return f"High risk vs {worst.seat_label} — consider folding before pushing this tile."


def _label_from_score(score: int) -> str:
    if score <= 0:
        return "genbutsu"
    if score <= 15:
        return "very-safe"
    if score <= 35:
        return "safe"
    if score <= 60:
        return "neutral"
    if score <= 85:
        return "warning"
    return "danger"


def _clamp(score: int) -> int:
    return max(0, min(100, int(score)))
