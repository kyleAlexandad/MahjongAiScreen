"""Per-player han (value) estimator.

Two flavours:

* **User**: full estimate that combines yaku directions detected by
  :mod:`yaku`, riichi state, total dora (normal + red), and a few simple
  rules (menzen, etc.).

* **Opponent**: visible-only estimate. Hidden tiles are not assumed; only
  open melds, riichi, and the visible part of dora indicators are
  counted. Always returned with ``estimate=True``.

This is a heuristic, not a real point/han calculator. Treat the numbers
as "rough lower bound" — the UI shows them with explicit "estimated"
labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from .game import (
    DRAGON_IDS,
    GameState,
    PlayerState,
    dora_tile_for,
    visible_aka_in_player,
)
from .tiles import Tile, tile_code


@dataclass
class HanEstimate:
    seat: int
    han: int
    yaku_han: int  # han from yaku only (riichi, yakuhai, tanyao, ...)
    dora_han: int  # han from dora indicators + aka dora
    has_yaku: bool  # True iff at least one yaku is detected for this seat
    estimate: bool
    notes: List[str] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seat": self.seat,
            "han": self.han,
            "yaku_han": self.yaku_han,
            "dora_han": self.dora_han,
            "has_yaku": self.has_yaku,
            "estimate": self.estimate,
            "notes": list(self.notes),
            "breakdown": dict(self.breakdown),
        }


# Keys in ``breakdown`` that count as "dora value" rather than "yaku value".
# Anything not in this set is summed into ``yaku_han``.
_DORA_BREAKDOWN_KEYS = {"dora", "aka_dora", "visible_dora", "visible_aka"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def estimate_all_han(state: GameState, yaku_info: Optional[dict] = None) -> List[dict]:
    """Return per-seat han estimates as serialisable dicts (seat 0..3)."""
    out: List[HanEstimate] = []
    out.append(_estimate_user_han(state, yaku_info or {}))
    for i, opp in enumerate(state.opponents, start=1):
        out.append(_estimate_opponent_han(state, opp, i))
    return [e.to_dict() for e in out]


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


def _estimate_user_han(state: GameState, yaku_info: dict) -> HanEstimate:
    """Estimate the user's han based on hand state + detected yaku directions."""
    breakdown: dict = {}
    notes: List[str] = []

    is_closed = all(m.type == "ankan" for m in state.user.melds) or len(state.user.melds) == 0
    han = 0

    # Riichi
    if state.user.riichi:
        han += 1
        breakdown["riichi"] = 1
        notes.append("Riichi (+1)")

    # Yakuhai — count completed yakuhai sets (triplets & melded pons/kans).
    yh = _count_user_yakuhai(state)
    if yh > 0:
        han += yh
        breakdown["yakuhai"] = yh
        notes.append(f"Yakuhai sets +{yh}")

    # Direction-based yaku (only count when confidence is high enough).
    directions = {d["name"]: d for d in (yaku_info.get("directions") or [])}

    def add_if_high(name: str, han_val_closed: int, han_val_open: int = None, threshold: int = 70):
        d = directions.get(name)
        if not d or d["confidence"] < threshold:
            return 0
        v = han_val_closed if is_closed else (han_val_open if han_val_open is not None else han_val_closed)
        return v

    tanyao = add_if_high("tanyao", 1)
    if tanyao:
        han += tanyao
        breakdown["tanyao"] = tanyao
        notes.append(f"Tanyao +{tanyao}")

    honitsu = add_if_high("honitsu", 3, 2)
    if honitsu:
        han += honitsu
        breakdown["honitsu"] = honitsu
        notes.append(f"Honitsu +{honitsu}")

    chinitsu = add_if_high("chinitsu", 6, 5)
    if chinitsu:
        han += chinitsu
        breakdown["chinitsu"] = chinitsu
        notes.append(f"Chinitsu +{chinitsu}")

    toitoi = add_if_high("toitoi", 2)
    if toitoi:
        han += toitoi
        breakdown["toitoi"] = toitoi
        notes.append(f"Toitoi +{toitoi}")

    chiitoi = add_if_high("chiitoitsu", 2)
    if chiitoi:
        han += chiitoi
        breakdown["chiitoitsu"] = chiitoi
        notes.append(f"Chiitoitsu +{chiitoi}")

    # Dora + aka dora (hand + every owned meld).
    dora = (yaku_info.get("value_hints") or {}).get("dora_in_hand", 0)
    aka = (yaku_info.get("value_hints") or {}).get("aka_dora_in_hand", 0)
    if dora:
        han += dora
        breakdown["dora"] = dora
        notes.append(f"Dora +{dora}")
    if aka:
        han += aka
        breakdown["aka_dora"] = aka
        notes.append(f"Aka dora +{aka}")

    yaku_han = sum(v for k, v in breakdown.items() if k not in _DORA_BREAKDOWN_KEYS)
    dora_han = breakdown.get("dora", 0) + breakdown.get("aka_dora", 0)
    has_yaku = yaku_han > 0
    if dora_han > 0 and not has_yaku:
        notes.append(
            "Dora alone is not a yaku — you still need a yaku such as Riichi, "
            "Yakuhai, or Tanyao to win."
        )

    return HanEstimate(
        seat=0,
        han=han,
        yaku_han=yaku_han,
        dora_han=dora_han,
        has_yaku=has_yaku,
        estimate=True,  # still an estimate — no formal yaku check yet
        notes=notes,
        breakdown=breakdown,
    )


def _count_user_yakuhai(state: GameState) -> int:
    """Count yakuhai sets the user definitely has.

    Concealed triplets count; pairs do not (they could become triplets but
    aren't yet). Open pons/kans of yakuhai count.
    """
    count = 0
    counts = state.hand_counts()
    # Concealed triplets of yakuhai. Round + seat wind on the same tile
    # is a double yakuhai (2 han).
    for tid in range(27, 34):
        if not _is_yakuhai_for(state, tid):
            continue
        if counts[tid] >= 3:
            if tid == state.round_wind and tid == state.seat_wind:
                count += 2
            else:
                count += 1
    # Open / ankan melds of yakuhai.
    for m in state.user.melds:
        if m.type in ("pon", "kan", "ankan") and m.tiles:
            t = m.tiles[0]
            if all(x == t for x in m.tiles) and _is_yakuhai_for(state, t):
                # Round + seat wind on the same tile is a double yakuhai.
                if t == state.round_wind and t == state.seat_wind:
                    count += 2
                else:
                    count += 1
    return count


def _is_yakuhai_for(state: GameState, tile_id: int) -> bool:
    if tile_id in DRAGON_IDS:
        return True
    if tile_id == state.round_wind:
        return True
    if tile_id == state.seat_wind:
        return True
    return False


# ---------------------------------------------------------------------------
# Opponent (visible only)
# ---------------------------------------------------------------------------


def _seat_wind_for_opponent(state: GameState, opp_seat: int) -> int:
    """Compute opponent's seat wind from the user's seat wind.

    Around the table play goes counter-clockwise: E → S → W → N → E.
    Seat indices (user-relative): 0=user, 1=shimocha (next), 2=toimen,
    3=kamicha (previous). So opponent ``i`` has seat wind = the user's
    seat wind shifted by ``+i`` positions in the [E,S,W,N] cycle.
    """
    winds = [27, 28, 29, 30]
    base = winds.index(state.seat_wind)
    return winds[(base + opp_seat) % 4]


def _estimate_opponent_han(
    state: GameState, opp: PlayerState, seat: int
) -> HanEstimate:
    breakdown: dict = {}
    notes: List[str] = []
    han = 0

    if opp.riichi:
        han += 1
        breakdown["riichi"] = 1
        notes.append("Riichi (+1)")

    # Visible yakuhai melds: round wind, this opp's seat wind, dragons.
    opp_seat_wind = _seat_wind_for_opponent(state, seat)
    yh = 0
    for m in opp.melds:
        if m.type in ("pon", "kan", "ankan") and m.tiles:
            t = m.tiles[0]
            if not all(x == t for x in m.tiles):
                continue
            is_yh = (
                t in DRAGON_IDS
                or t == state.round_wind
                or t == opp_seat_wind
            )
            if is_yh:
                if t == state.round_wind and t == opp_seat_wind:
                    yh += 2  # double wind
                else:
                    yh += 1
    if yh:
        han += yh
        breakdown["visible_yakuhai"] = yh
        notes.append(f"Visible yakuhai melds +{yh}")

    # Visible dora in opp's melds.
    dora_tiles_set = set(dora_tile_for(t) for t in state.dora_indicators)
    visible_dora = 0
    for m in opp.melds:
        for t in m.tiles:
            if t in dora_tiles_set:
                visible_dora += 1
    if visible_dora:
        han += visible_dora
        breakdown["visible_dora"] = visible_dora
        notes.append(f"Visible dora +{visible_dora}")

    # Visible aka dora.
    aka = visible_aka_in_player(opp)
    if aka:
        han += aka
        breakdown["visible_aka"] = aka
        notes.append(f"Visible aka dora +{aka}")

    yaku_han = sum(v for k, v in breakdown.items() if k not in _DORA_BREAKDOWN_KEYS)
    dora_han = breakdown.get("visible_dora", 0) + breakdown.get("visible_aka", 0)
    has_yaku = yaku_han > 0

    return HanEstimate(
        seat=seat,
        han=han,
        yaku_han=yaku_han,
        dora_han=dora_han,
        has_yaku=has_yaku,
        estimate=True,
        notes=notes,
        breakdown=breakdown,
    )
