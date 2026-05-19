"""Call-opportunity analysis (chi / pon / kan / ron / pass) for the user.

Given a :class:`GameState` and the tile that some opponent just discarded,
this module enumerates the user's legal call options, simulates each one,
and returns a beginner-friendly recommendation:

* Is the call **legal** at all?
* Does it **reduce shanten**?
* Does it create a clean **yakuhai** (round / seat wind / dragon triplet)?
* Is it likely to **open the hand without a yaku** (a common beginner trap)?
* Is anyone in **riichi** (push/fold pressure)?

The result is a list of :class:`CallOption` objects with a 0..100 score
and short notes that the frontend renders as the "AI recommendation"
chip near the call buttons.

This is intentionally heuristic — full yaku enumeration is out of scope
for Phase 2. The score and explanations should be read as guidance, not
as ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .game import DRAGON_IDS, GameState, Meld
from .legality import (
    can_user_open_kan,
    can_user_pon,
    get_legal_chi_options,
)
from .shanten import calculate_shanten
from .tiles import NUM_TILES, Tile, tile_code, tile_short_name


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class CallOption:
    action: str  # 'chi' | 'pon' | 'kan' | 'ron' | 'pass'
    legal: bool = False
    recommended: bool = False
    score: int = 0
    shanten_before: Optional[int] = None
    shanten_after: Optional[int] = None
    consumed_tiles: List[int] = field(default_factory=list)
    """Tiles the user would surrender from their concealed hand to make this
    call. Empty for ``ron`` and ``pass`` (no tiles leave the hand)."""
    notes: List[str] = field(default_factory=list)
    yaku_hint: Optional[str] = None
    """Coarse yaku hint: ``'yakuhai'`` (instant 1-han via round/seat wind or
    dragon triplet) or ``None`` so far. More can be added later."""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "legal": self.legal,
            "recommended": self.recommended,
            "score": self.score,
            "shanten_before": self.shanten_before,
            "shanten_after": self.shanten_after,
            "consumed_tiles": [tile_code(t) for t in self.consumed_tiles],
            "consumed_tile_ids": list(self.consumed_tiles),
            "notes": list(self.notes),
            "yaku_hint": self.yaku_hint,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze_call(
    state: GameState, discarded_tile: int, discarder_seat: int
) -> dict:
    """Analyse the user's call options on ``discarded_tile`` discarded by
    ``discarder_seat`` (1=shimocha / 2=toimen / 3=kamicha; 0=user — not
    a real call opportunity but accepted for symmetry)."""
    if not 0 <= discarded_tile < NUM_TILES:
        raise ValueError(f"discarded tile id out of range: {discarded_tile}")
    if not 0 <= discarder_seat <= 3:
        raise ValueError(f"discarder seat out of range: {discarder_seat}")

    counts = state.hand_counts()
    open_melds = len(state.user.melds)
    sh_before = calculate_shanten(counts, open_melds_count=open_melds)
    any_riichi = any(opp.riichi for opp in state.opponents)

    options: List[CallOption] = []
    options.append(_analyze_pon(state, counts, discarded_tile, discarder_seat,
                                sh_before, open_melds, any_riichi))
    options.append(_analyze_kan(state, counts, discarded_tile, discarder_seat,
                                sh_before, open_melds, any_riichi))
    options.append(_analyze_chi(state, counts, discarded_tile, discarder_seat,
                                sh_before, open_melds, any_riichi))
    options.append(_analyze_ron(state, counts, discarded_tile, discarder_seat,
                                sh_before, open_melds))
    options.append(_analyze_pass(sh_before))

    legal_actions = [o.action for o in options if o.legal and o.action != "pass"]

    # Pick the recommended action: prefer the highest-scoring legal option
    # that is itself flagged ``recommended``. Always prefer Ron when legal.
    ron = next((o for o in options if o.action == "ron" and o.legal), None)
    if ron:
        recommended_action = "ron"
    else:
        rec = max(
            (o for o in options if o.legal and o.recommended),
            key=lambda o: o.score,
            default=None,
        )
        recommended_action = rec.action if rec else "pass"

    return {
        "discarded_tile": tile_code(discarded_tile),
        "discarded_tile_id": discarded_tile,
        "discarder_seat": discarder_seat,
        "shanten_before": sh_before,
        "legal_actions": legal_actions,
        "recommended_action": recommended_action,
        "options": [o.to_dict() for o in options],
    }


# ---------------------------------------------------------------------------
# Per-action analysers
# ---------------------------------------------------------------------------


def _is_yakuhai(state: GameState, tile_id: int) -> bool:
    if tile_id in DRAGON_IDS:
        return True
    if tile_id == state.round_wind:
        return True
    if tile_id == state.seat_wind:
        return True
    return False


def _hand_is_closed(state: GameState) -> bool:
    return all(m.type == "ankan" for m in state.user.melds) or len(state.user.melds) == 0


def _analyze_pon(
    state: GameState,
    counts: list[int],
    tile_id: int,
    discarder: int,
    sh_before: int,
    open_melds: int,
    any_riichi: bool,
) -> CallOption:
    opt = CallOption(action="pon", shanten_before=sh_before)
    if discarder == 0 or not can_user_pon(state, tile_id):
        opt.legal = False
        return opt

    sim = list(counts)
    sim[tile_id] -= 2
    sh_after = calculate_shanten(sim, open_melds_count=open_melds + 1)
    opt.legal = True
    opt.shanten_after = sh_after
    opt.consumed_tiles = [tile_id, tile_id]

    yakuhai = _is_yakuhai(state, tile_id)
    if yakuhai:
        opt.yaku_hint = "yakuhai"
    score = 50

    if yakuhai:
        score += 30
        opt.notes.append(_yakuhai_note(state, tile_id))
    if sh_after < sh_before:
        score += 15 * (sh_before - sh_after)
        opt.notes.append(_shanten_note(sh_before, sh_after))
    elif sh_after == sh_before:
        score -= 15
        opt.notes.append("Shanten doesn't change.")
    else:
        score -= 25
        opt.notes.append("Shanten gets worse.")

    if _hand_is_closed(state) and not yakuhai and sh_before > 1:
        score -= 25
        opt.notes.append("Opens a closed hand without an obvious yaku — risky.")
    if any_riichi:
        score -= 20
        opt.notes.append("An opponent is in riichi — push only with a clear plan.")

    score = max(0, min(100, score))
    opt.score = score
    opt.recommended = score >= 60 or (yakuhai and sh_after <= sh_before)
    return opt


def _analyze_kan(
    state: GameState,
    counts: list[int],
    tile_id: int,
    discarder: int,
    sh_before: int,
    open_melds: int,
    any_riichi: bool,
) -> CallOption:
    opt = CallOption(action="kan", shanten_before=sh_before)
    if discarder == 0 or not can_user_open_kan(state, tile_id):
        opt.legal = False
        return opt

    sim = list(counts)
    sim[tile_id] -= 3
    sh_after = calculate_shanten(sim, open_melds_count=open_melds + 1)
    opt.legal = True
    opt.shanten_after = sh_after
    opt.consumed_tiles = [tile_id, tile_id, tile_id]

    yakuhai = _is_yakuhai(state, tile_id)
    if yakuhai:
        opt.yaku_hint = "yakuhai"
    score = 45

    if yakuhai:
        score += 25
        opt.notes.append(_yakuhai_note(state, tile_id))
    if sh_after < sh_before:
        score += 12 * (sh_before - sh_after)
    elif sh_after == sh_before:
        score -= 5
        opt.notes.append("Pon would usually be more flexible than kan here.")
    else:
        score -= 25
    if any_riichi:
        score -= 25
        opt.notes.append("Open kan reveals a new dora; risky against a riichi.")

    score = max(0, min(100, score))
    opt.score = score
    opt.recommended = yakuhai and sh_after <= sh_before
    return opt


def _analyze_chi(
    state: GameState,
    counts: list[int],
    tile_id: int,
    discarder: int,
    sh_before: int,
    open_melds: int,
    any_riichi: bool,
) -> CallOption:
    opt = CallOption(action="chi", shanten_before=sh_before)
    # Chi is legal only off kamicha; honors and missing-tile shapes are
    # already filtered by the legality helper.
    candidate_pairs = get_legal_chi_options(state, tile_id, discarder, caller_seat=0)
    if not candidate_pairs:
        opt.legal = False
        return opt

    # Pick the shape that produces the lowest shanten.
    best_after = None
    best_pair: Tuple[int, int] = candidate_pairs[0]
    for a, b in candidate_pairs:
        sim = list(counts)
        sim[a] -= 1
        sim[b] -= 1
        sh_after = calculate_shanten(sim, open_melds_count=open_melds + 1)
        if best_after is None or sh_after < best_after:
            best_after = sh_after
            best_pair = (a, b)

    opt.legal = True
    opt.shanten_after = best_after
    opt.consumed_tiles = list(best_pair)

    score = 40
    if best_after < sh_before:
        score += 12 * (sh_before - best_after)
        opt.notes.append(_shanten_note(sh_before, best_after))
    elif best_after == sh_before:
        score -= 18
        opt.notes.append("Shanten doesn't change.")
    else:
        score -= 30

    if _hand_is_closed(state) and sh_before > 1:
        score -= 20
        opt.notes.append("Opens a closed hand without locking in a yaku.")
    if any_riichi:
        score -= 20
        opt.notes.append("An opponent is in riichi — opening the hand is risky.")

    score = max(0, min(100, score))
    opt.score = score
    opt.recommended = score >= 65 and best_after <= sh_before - 1
    return opt


def _analyze_ron(
    state: GameState,
    counts: list[int],
    tile_id: int,
    discarder: int,
    sh_before: int,
    open_melds: int,
) -> CallOption:
    opt = CallOption(action="ron", shanten_before=sh_before)
    if discarder == 0:
        opt.legal = False
        return opt

    # Simulate: add the tile to the closed hand and check for shanten == -1.
    sim = list(counts)
    sim[tile_id] += 1
    sh_after = calculate_shanten(sim, open_melds_count=open_melds)
    if sh_after >= 0:
        opt.legal = False
        opt.shanten_after = sh_after
        return opt

    opt.legal = True
    opt.recommended = True
    opt.score = 100
    opt.shanten_after = sh_after
    opt.notes.append("Winning hand detected. Verify yaku before declaring Ron.")
    opt.yaku_hint = "winning"
    return opt


def _analyze_pass(sh_before: int) -> CallOption:
    return CallOption(
        action="pass",
        legal=True,
        recommended=False,
        score=0,
        shanten_before=sh_before,
        shanten_after=sh_before,
        notes=["Pass keeps the hand closed and waits for a better tile."],
    )


# ---------------------------------------------------------------------------
# Note helpers
# ---------------------------------------------------------------------------


def _yakuhai_note(state: GameState, tile_id: int) -> str:
    if tile_id in DRAGON_IDS:
        return f"Dragon ({Tile(tile_id).long_name}) — instant yakuhai once melded."
    if tile_id == state.round_wind and tile_id == state.seat_wind:
        return "Double wind (round + seat) — strong yakuhai."
    if tile_id == state.round_wind:
        return "Round wind — yakuhai for everybody at the table."
    if tile_id == state.seat_wind:
        return "Your seat wind — yakuhai for you only."
    return "Yakuhai tile."


def _shanten_note(before: int, after: int) -> str:
    return f"Shanten improves from {before} to {after}."
