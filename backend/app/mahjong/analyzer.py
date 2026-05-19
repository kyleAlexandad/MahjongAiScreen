"""High-level analysis: discard recommendation + beginner-friendly explanation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .defense import TileDanger, assess_tile_danger
from .evaluation import (
    discard_expected_value,
    draws_left,
    estimate_opponent_value,
    estimate_self_value,
    weighted_acceptance,
    win_probability,
)
from .game import GameState, dora_tiles
from .han import estimate_all_han
from .shanten import (
    ShantenBreakdown,
    calculate_shanten,
    calculate_shanten_breakdown,
)
from .tiles import AKA_TILE_IDS, NUM_TILES, tile_code, tile_short_name
from .ukeire import calculate_ukeire, total_ukeire
from .visibility import remaining_counts, visible_counts
from .yaku import analyze_yaku_directions


@dataclass
class DiscardCandidate:
    """A possible discard, scored by the resulting shanten, ukeire and danger."""

    tile_id: int
    tile_code: str
    shanten_after: int
    ukeire: Dict[int, int] = field(default_factory=dict)
    ukeire_count: int = 0
    danger: Optional[TileDanger] = None
    combined_score: float = 0.0
    """Higher = better. 0..100 display score derived from the EV ranking."""
    is_dora: bool = False
    """True when discarding this tile gives up an active dora."""
    acceptance_quality: float = 0.0
    """Two-step weighted acceptance (ukeire²) of the resulting shape."""
    win_p: Optional[float] = None
    """Estimated probability this resulting shape eventually wins."""
    value_estimate: Optional[int] = None
    """Estimated points if the hand is completed (han→points)."""
    expected_value: Optional[float] = None
    """EV in points: win_p*self_value − Σ dealin_p*opponent_value."""

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "tile_code": self.tile_code,
            "shanten_after": self.shanten_after,
            "ukeire_count": self.ukeire_count,
            "ukeire": [
                {"tile_id": t, "tile_code": tile_code(t), "remaining": n}
                for t, n in sorted(self.ukeire.items())
            ],
            "danger": self.danger.to_dict() if self.danger else None,
            "combined_score": round(self.combined_score, 2),
            "is_dora": self.is_dora,
            "acceptance_quality": round(self.acceptance_quality, 1),
            "win_p": round(self.win_p, 4) if self.win_p is not None else None,
            "value_estimate": self.value_estimate,
            "expected_value": (
                round(self.expected_value, 1)
                if self.expected_value is not None
                else None
            ),
        }


def recommend_discards(counts: Sequence[int]) -> List[DiscardCandidate]:
    """Evaluate every distinct discard for a 14-tile hand.

    Sorted best-first by ``(shanten_after, -ukeire_count, tile_id)``.
    """
    if sum(counts) != 14:
        raise ValueError(f"recommend_discards expects 14 tiles, got {sum(counts)}")
    return _ranked_discards(list(counts))


def analyze_hand(counts: Sequence[int]) -> dict:
    """Top-level analysis used by the *quick* API (no game state).

    Works for both 13-tile (no draw yet) and 14-tile (post-draw) hands.
    """
    n = sum(counts)
    if n not in (13, 14):
        raise ValueError(f"hand size must be 13 or 14, got {n}")

    breakdown = calculate_shanten_breakdown(counts)
    payload: dict = {
        "tile_count": n,
        "shanten": breakdown.overall,
        "shanten_breakdown": {
            "normal": breakdown.normal,
            "chiitoitsu": breakdown.chiitoitsu,
            "kokushi": breakdown.kokushi,
            "best_form": breakdown.best_form,
        },
        "is_winning": breakdown.overall < 0,
        "is_tenpai": breakdown.overall == 0,
    }

    if n == 13:
        uke = calculate_ukeire(counts, current_shanten=breakdown.overall)
        payload["ukeire"] = [
            {"tile_id": t, "tile_code": tile_code(t), "remaining": r}
            for t, r in sorted(uke.items())
        ]
        payload["ukeire_count"] = total_ukeire(uke)
        payload["discards"] = []
        payload["best_discard"] = None
        payload["explanation"] = _explain_13(breakdown, payload["ukeire_count"])
        return payload

    candidates = _ranked_discards(list(counts))
    best = candidates[0] if candidates else None
    payload["discards"] = [c.to_dict() for c in candidates]
    payload["best_discard"] = best.to_dict() if best else None
    payload["ukeire"] = best.to_dict()["ukeire"] if best else []
    payload["ukeire_count"] = best.ukeire_count if best else 0
    payload["explanation"] = _explain_14(breakdown, candidates)
    return payload


def analyze_game(state: GameState) -> dict:
    """Full analysis aware of opponents, dora, riichi, visibility and defense.

    Open melds (chi/pon/kan/ankan) reduce the closed-hand size by 3 each;
    they are accounted for in the shanten formula automatically.
    """
    counts = state.hand_counts()
    n = sum(counts)
    open_melds_count = len(state.user.melds)
    expected_between = 13 - 3 * open_melds_count
    expected_after_draw = 14 - 3 * open_melds_count
    if n not in (expected_between, expected_after_draw):
        raise ValueError(
            f"closed hand has {n} tiles; with {open_melds_count} open meld(s) "
            f"expected {expected_between} (between turns) or {expected_after_draw} (post-draw)"
        )

    visible = visible_counts(state)
    remaining = remaining_counts(state)
    breakdown = calculate_shanten_breakdown(counts, open_melds_count)

    dora = dora_tiles(state.dora_indicators)
    threats = [
        {"seat": idx + 1, "label": "shimocha" if idx == 0 else "toimen" if idx == 1 else "kamicha"}
        for idx, opp in enumerate(state.opponents)
        if opp.riichi
    ]

    yaku_info = analyze_yaku_directions(state)
    han_estimates = estimate_all_han(state, yaku_info)
    payload: dict = {
        "tile_count": n,
        "shanten": breakdown.overall,
        "shanten_breakdown": {
            "normal": breakdown.normal,
            "chiitoitsu": breakdown.chiitoitsu,
            "kokushi": breakdown.kokushi,
            "best_form": breakdown.best_form,
        },
        "is_winning": breakdown.overall < 0,
        "is_tenpai": breakdown.overall == 0,
        "dora_tiles": [tile_code(t) for t in dora],
        "dora_tile_ids": [],  # populated from yaku_info.value_hints just below
        "threats": threats,
        "visible_total": sum(visible),
        # Yaku-direction layer (Phase 2.6).
        "yaku_directions": yaku_info["directions"],
        "value_hints": yaku_info["value_hints"],
        "tile_reasons": yaku_info["tile_reasons"],
        # Per-player han estimates (Phase 2.8).
        "han_estimates": han_estimates,
    }
    # Add raw dora tile ids (frontend uses them for highlighting).
    payload["dora_tile_ids"] = list(yaku_info["value_hints"].get("dora_tile_ids", []))

    if n == expected_between:
        uke = calculate_ukeire(
            counts,
            current_shanten=breakdown.overall,
            remaining=remaining,
            open_melds_count=open_melds_count,
        )
        payload["ukeire"] = [
            {"tile_id": t, "tile_code": tile_code(t), "remaining": r}
            for t, r in sorted(uke.items())
        ]
        payload["ukeire_count"] = total_ukeire(uke)
        payload["discards"] = []
        payload["best_discard"] = None
        payload["explanation"] = _explain_13(
            breakdown, payload["ukeire_count"], yaku_info
        )
        return payload

    # post-draw: rank discards using both efficiency and defense.
    candidates = _ranked_discards_with_defense(
        list(counts),
        state=state,
        visible=visible,
        remaining=remaining,
        open_melds_count=open_melds_count,
        han_estimates=han_estimates,
    )
    best = candidates[0] if candidates else None
    payload["discards"] = [c.to_dict() for c in candidates]
    payload["best_discard"] = best.to_dict() if best else None
    payload["ukeire"] = best.to_dict()["ukeire"] if best else []
    payload["ukeire_count"] = best.ukeire_count if best else 0
    payload["explanation"] = _explain_14_with_defense(
        breakdown, candidates, threats, yaku_info
    )
    return payload


def _ranked_discards(counts: list[int]) -> List[DiscardCandidate]:
    out: List[DiscardCandidate] = []
    for tid in range(NUM_TILES):
        if counts[tid] == 0:
            continue
        counts[tid] -= 1
        shanten = calculate_shanten(counts)
        uke = calculate_ukeire(counts, current_shanten=shanten)
        counts[tid] += 1
        out.append(
            DiscardCandidate(
                tile_id=tid,
                tile_code=tile_code(tid),
                shanten_after=shanten,
                ukeire=uke,
                ukeire_count=total_ukeire(uke),
            )
        )
    out.sort(key=lambda c: (c.shanten_after, -c.ukeire_count, c.tile_id))
    return out


def _ranked_discards_with_defense(
    counts: list[int],
    state: GameState,
    visible: Sequence[int],
    remaining: Sequence[int],
    open_melds_count: int = 0,
    han_estimates: Optional[List[dict]] = None,
) -> List[DiscardCandidate]:
    """Rank every distinct discard by **expected value**.

        EV = P(win | resulting shape) * value(our hand)
             - Σ_opponent P(deal in) * value(opponent)

    With nobody threatening, the cost term is tiny and EV tracks pure
    efficiency (shanten dominates via the win-probability curve). When an
    opponent is in riichi the cost term is real points, so dangerous tiles
    are folded and safe ones pushed — a genuine push/fold decision rather
    than the old fixed efficiency/safety blend.
    """
    from .game import dora_tile_for

    dora_set = set(dora_tile_for(t) for t in state.dora_indicators)
    is_closed = (
        all(m.type == "ankan" for m in state.user.melds)
        or len(state.user.melds) == 0
    )
    han_estimates = han_estimates or estimate_all_han(state)
    draws = draws_left(state)

    # Opponent (value, riichi) is independent of which tile we drop.
    opp_meta = [
        (
            estimate_opponent_value(state, han_estimates, seat),
            state.player(seat).riichi,
        )
        for seat in (1, 2, 3)
    ]

    # Pass 1: shanten / ukeire / danger for every candidate.
    raw: List[tuple[int, int, dict, TileDanger]] = []
    for tid in range(NUM_TILES):
        if counts[tid] == 0:
            continue
        counts[tid] -= 1
        shanten = calculate_shanten(counts, open_melds_count)
        uke = calculate_ukeire(
            counts,
            current_shanten=shanten,
            remaining=remaining,
            open_melds_count=open_melds_count,
        )
        counts[tid] += 1
        danger = assess_tile_danger(tid, state, visible)
        raw.append((tid, shanten, uke, danger))

    if not raw:
        return []
    min_shanten = min(sh for _, sh, _, _ in raw)
    self_value = estimate_self_value(
        state, han_estimates, min_shanten, is_closed=is_closed
    )

    out: List[DiscardCandidate] = []
    for tid, shanten, uke, danger in raw:
        uke_count = total_ukeire(uke)
        # The 2-step expansion is the expensive part — only run it for the
        # shapes that can realistically be chosen (best shanten, plus the
        # one-worse tier that matters for fold decisions).
        if shanten <= min_shanten + 1:
            counts[tid] -= 1
            _, quality = weighted_acceptance(
                counts, remaining, open_melds_count, shanten
            )
            counts[tid] += 1
        else:
            quality = float(uke_count)

        win_p = win_probability(
            shanten, uke_count, quality, draws, is_closed=is_closed
        )
        per_opp = [
            (
                next(
                    (
                        o.score
                        for o in danger.per_opponent
                        if o.seat == seat
                    ),
                    danger.score,
                ),
                opp_meta[seat - 1][0],
                opp_meta[seat - 1][1],
            )
            for seat in (1, 2, 3)
        ]
        ev = discard_expected_value(win_p, self_value, per_opp)

        cand = DiscardCandidate(
            tile_id=tid,
            tile_code=tile_code(tid),
            shanten_after=shanten,
            ukeire=uke,
            ukeire_count=uke_count,
            danger=danger,
            acceptance_quality=quality,
            win_p=win_p,
            value_estimate=self_value,
            expected_value=ev.ev,
        )
        cand.is_dora = tid in dora_set
        out.append(cand)

    # Best EV first; ties broken deterministically by tile id.
    out.sort(key=lambda c: (-(c.expected_value or 0.0), c.tile_id))

    # Map EV onto a 0..100 display score (best = 100). Keeps the UI's
    # existing `combined_score` field meaningful without leaking raw points.
    evs = [c.expected_value or 0.0 for c in out]
    hi, lo = max(evs), min(evs)
    span = (hi - lo) or 1.0
    for c in out:
        c.combined_score = round(100.0 * ((c.expected_value or 0.0) - lo) / span, 2)
    return out


# ---------------------------------------------------------------------------
# Explanations (short, beginner-friendly)
# ---------------------------------------------------------------------------


def _shanten_label(shanten: int) -> str:
    if shanten < 0:
        return "winning hand (agari)"
    if shanten == 0:
        return "tenpai"
    if shanten == 1:
        return "1-shanten"
    return f"{shanten}-shanten"


def _explain_13(
    breakdown: ShantenBreakdown, ukeire_count: int, yaku_info: Optional[dict] = None
) -> str:
    lines: list[str] = []
    lines.append(f"Your hand is {_shanten_label(breakdown.overall)}.")
    if breakdown.overall < 0:
        lines.append("It's already a complete winning shape.")
        return " ".join(lines)
    if breakdown.overall == 0:
        lines.append(
            f"You are tenpai with {ukeire_count} winning tiles available "
            f"({_form_label(breakdown.best_form)} form)."
        )
    else:
        lines.append(
            f"You need {ukeire_count} different effective tiles "
            f"to advance toward {_form_label(breakdown.best_form)}."
        )
    if yaku_info and yaku_info.get("directions"):
        top_dir = yaku_info["directions"][0]
        lines.append(
            f"Yaku direction: {top_dir['label_en']} (confidence {top_dir['confidence']}/100)."
        )
    return " ".join(lines)


def _explain_14(breakdown: ShantenBreakdown, candidates: List[DiscardCandidate]) -> str:
    if not candidates:
        return "No discards available."
    best = candidates[0]
    parts: list[str] = []
    parts.append(f"Current hand: {_shanten_label(breakdown.overall)} ({_form_label(breakdown.best_form)} form).")

    after = _shanten_label(best.shanten_after)
    parts.append(
        f"Discard {tile_short_name(best.tile_id)}: stays at {after} "
        f"with {best.ukeire_count} effective tiles "
        f"({len(best.ukeire)} kinds)."
    )

    near = [c for c in candidates[1:4] if c.shanten_after == best.shanten_after]
    if near:
        rivals = ", ".join(
            f"{tile_short_name(c.tile_id)} ({c.ukeire_count})" for c in near
        )
        parts.append(f"Close alternatives: {rivals}.")

    return " ".join(parts)


def _explain_14_with_defense(
    breakdown: ShantenBreakdown,
    candidates: List[DiscardCandidate],
    threats: List[dict],
    yaku_info: Optional[dict] = None,
) -> str:
    if not candidates:
        return "No discards available."
    best = candidates[0]
    parts: list[str] = []
    parts.append(
        f"Current hand: {_shanten_label(breakdown.overall)} "
        f"({_form_label(breakdown.best_form)} form)."
    )
    after = _shanten_label(best.shanten_after)
    danger_part = ""
    if best.danger is not None:
        danger_part = f" — danger {best.danger.score}/100 ({best.danger.label})"
    parts.append(
        f"Best discard: {tile_short_name(best.tile_id)} → {after} "
        f"with {best.ukeire_count} ukeire ({len(best.ukeire)} kinds){danger_part}."
    )
    if best.win_p is not None and best.value_estimate is not None:
        parts.append(
            f"Estimated win rate ≈ {round(best.win_p * 100)}% at "
            f"~{best.value_estimate} pts (EV-ranked)."
        )
    if yaku_info and yaku_info.get("directions"):
        top_dir = yaku_info["directions"][0]
        parts.append(
            f"Yaku direction: {top_dir['label_en']} (confidence {top_dir['confidence']}/100)."
        )
        if yaku_info["value_hints"].get("dora_in_hand", 0):
            parts.append(
                f"Dora in hand: {yaku_info['value_hints']['dora_in_hand']}."
            )
    if best.danger and best.danger.summary:
        parts.append(best.danger.summary)
    if threats:
        threat_labels = ", ".join(t["label"] for t in threats)
        parts.append(f"Threats: {threat_labels} in riichi — defence is weighted higher.")
    return " ".join(parts)


def _form_label(form: str) -> str:
    return {
        "normal": "standard 4 melds + pair",
        "chiitoitsu": "seven pairs (chiitoitsu)",
        "kokushi": "thirteen orphans (kokushi musou)",
    }.get(form, form)
