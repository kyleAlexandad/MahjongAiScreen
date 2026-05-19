"""Yaku-DIRECTION detection (not a full yaku scorer).

This module looks at a 13- or 14-tile hand (closed counts + the user's
open melds in the :class:`GameState`) and reports:

* which yaku the hand is **moving toward** (tanyao / yakuhai / honitsu /
  chinitsu / toitoi / chiitoitsu / kokushi / honroutou),
* per-tile reason hints the UI can stick on the user's hand
  ("Keep for Honitsu", "Yakuhai", "Dora", "Dangerous"),
* simple value hints (in-hand dora count, yakuhai pairs).

Why "direction" rather than full yaku evaluation? Full yaku scoring
requires enumerating winning hand decompositions, applying the riichi
rule-set, fu calculation, and a long list of edge cases (rinshan,
chankan, haitei, etc.). That's a multi-week project on its own.
The direction detector covers ~95% of "what's the AI thinking?" for a
beginner without that complexity, and fits cleanly on top of the
existing shanten + ukeire engine.

Hand-shape heuristics
---------------------
* **Tanyao** : few terminals/honors → likely all-simples.
* **Yakuhai**: pair or triplet of round/seat wind / dragon → instant 1-han.
* **Honitsu**: one suit + honors dominate (>= 11 of 13 tiles).
* **Chinitsu**: one suit only (>= 11 of 13 tiles, no honors).
* **Toitoi** : pairs/triplets dominate, no chi melds.
* **Chiitoitsu**: chiitoi shanten <= 2.
* **Kokushi** : kokushi shanten <= 5 and many yaochuhai unique types.
* **Honroutou**: hand is yaochuhai-only.

Each direction returns a 0..100 confidence and a list of *keep* tile ids.
The frontend turns those keep ids into "Keep for X" hints on the user's
hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .game import DRAGON_IDS, GameState, total_user_aka
from .shanten import calculate_shanten, calculate_shanten_breakdown
from .tiles import NUM_TILES, Tile, YAOCHU_IDS, tile_code


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class YakuDirection:
    name: str               # canonical key, e.g. "tanyao"
    label_en: str
    label_zh: str
    confidence: int         # 0..100
    notes: List[str] = field(default_factory=list)
    keep_tile_ids: List[int] = field(default_factory=list)
    avoid_tile_ids: List[int] = field(default_factory=list)
    """Tiles that, if discarded, *break* this direction. Used by the UI to
    paint a small "breaks Tanyao / Honitsu" warning on those tiles."""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label_en": self.label_en,
            "label_zh": self.label_zh,
            "confidence": self.confidence,
            "notes": list(self.notes),
            "keep_tile_ids": list(self.keep_tile_ids),
            "keep_tile_codes": [tile_code(t) for t in self.keep_tile_ids],
            "avoid_tile_ids": list(self.avoid_tile_ids),
            "avoid_tile_codes": [tile_code(t) for t in self.avoid_tile_ids],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_yaku_directions(
    state: GameState,
    *,
    min_confidence: int = 30,
) -> dict:
    """Return a serializable dict of {directions, value_hints, tile_reasons}.

    ``tile_reasons`` is a mapping ``{tile_id: [reason_key, ...]}`` where
    ``reason_key`` is one of:
        ``"yakuhai"``, ``"dora"``, ``"keep_honitsu"``, ``"keep_chinitsu"``,
        ``"keep_tanyao"``, ``"keep_toitoi"``, ``"keep_kokushi"``,
        ``"break_tanyao"``, ``"break_honitsu"``, ``"break_chinitsu"``.
    """
    counts = state.hand_counts()
    open_melds = state.user.melds
    is_closed = len(open_melds) == 0

    directions: List[YakuDirection] = []
    directions.append(_check_tanyao(counts, state, open_melds))
    directions.extend(_check_yakuhai(counts, state, open_melds))
    directions.append(_check_honitsu(counts, state, open_melds))
    directions.append(_check_chinitsu(counts, state, open_melds))
    directions.append(_check_toitoi(counts, state, open_melds))
    if is_closed:
        directions.append(_check_chiitoitsu(counts))
        directions.append(_check_kokushi(counts))
    directions.append(_check_honroutou(counts, state, open_melds))

    directions = [d for d in directions if d.confidence >= min_confidence]
    directions.sort(key=lambda d: -d.confidence)

    value_hints = _value_hints(state, counts)
    tile_reasons = _per_tile_reasons(directions, state, counts, value_hints)

    return {
        "directions": [d.to_dict() for d in directions],
        "value_hints": value_hints,
        "tile_reasons": {
            str(tid): reasons for tid, reasons in sorted(tile_reasons.items())
        },
    }


# ---------------------------------------------------------------------------
# Direction checks
# ---------------------------------------------------------------------------


def _suit_counts(counts: Sequence[int]) -> Dict[str, int]:
    return {
        "m": sum(counts[0:9]),
        "p": sum(counts[9:18]),
        "s": sum(counts[18:27]),
        "z": sum(counts[27:34]),
    }


def _yaochu_count(counts: Sequence[int]) -> int:
    return sum(counts[t] for t in YAOCHU_IDS)


def _simples_only(counts: Sequence[int]) -> List[int]:
    """Return tile ids of simples (2-8 in numbered suits) present in hand."""
    out = []
    for tid in range(27):
        n = (tid % 9) + 1
        if 2 <= n <= 8 and counts[tid] > 0:
            out.append(tid)
    return out


def _is_yakuhai(state: GameState, tile_id: int) -> bool:
    if tile_id in DRAGON_IDS:
        return True
    if tile_id == state.round_wind:
        return True
    if tile_id == state.seat_wind:
        return True
    return False


def _meld_breaks_tanyao(open_melds) -> bool:
    for m in open_melds:
        for tid in m.tiles:
            if tid in YAOCHU_IDS:
                return True
    return False


def _meld_breaks_honitsu(open_melds, suit: str) -> bool:
    suit_base = {"m": 0, "p": 9, "s": 18, "z": 27}[suit]
    suit_end = suit_base + (7 if suit == "z" else 9)
    for m in open_melds:
        for tid in m.tiles:
            in_suit = suit_base <= tid < suit_end
            in_honors = tid >= 27
            # honitsu allows the chosen number suit + honors only
            if suit != "z":
                if not (in_suit or in_honors):
                    return True
            else:
                if not in_honors:
                    return True
    return False


def _check_tanyao(counts, state, open_melds) -> YakuDirection:
    yaochu = _yaochu_count(counts)
    if _meld_breaks_tanyao(open_melds):
        return YakuDirection("tanyao", "All Simples (Tanyao)", "断幺九", 0)
    # Confidence: 13 = no yaochu yet -> 100; +25 penalty per yaochu tile.
    confidence = max(0, 100 - 22 * yaochu)
    keep = _simples_only(counts)
    avoid = [t for t in range(34) if counts[t] > 0 and t in YAOCHU_IDS]
    notes = []
    if confidence >= 60:
        notes.append("Hand is mostly simples — Tanyao within reach.")
    elif confidence >= 30:
        notes.append("Tanyao still possible if terminals/honors are discarded.")
    return YakuDirection(
        "tanyao", "All Simples (Tanyao)", "断幺九",
        confidence, notes=notes, keep_tile_ids=keep, avoid_tile_ids=avoid,
    )


def _check_yakuhai(counts, state, open_melds) -> List[YakuDirection]:
    out: List[YakuDirection] = []
    # Look at every honor that is yakuhai for this player. For each one:
    #   count >= 3 -> already complete, very high confidence
    #   count == 2 -> "watching for the 3rd", high confidence
    #   count == 1 -> low confidence (one tile far from forming a triplet)
    # Open melds of a yakuhai also count as completed.
    open_meld_yakuhai = set()
    for m in open_melds:
        if not m.tiles:
            continue
        first = m.tiles[0]
        if all(t == first for t in m.tiles) and _is_yakuhai(state, first):
            open_meld_yakuhai.add(first)

    for tid in range(27, 34):
        if not _is_yakuhai(state, tid):
            continue
        in_hand = counts[tid]
        if tid in open_meld_yakuhai:
            confidence = 100
            note = f"Already melded yakuhai ({Tile(tid).long_name}) — yaku locked in."
            keep = []
        elif in_hand >= 3:
            confidence = 95
            note = f"Concealed triplet of {Tile(tid).long_name} — yakuhai ready."
            keep = [tid]
        elif in_hand == 2:
            confidence = 75
            note = f"Pair of {Tile(tid).long_name} — call Pon for an instant yakuhai."
            keep = [tid]
        elif in_hand == 1:
            confidence = 30
            note = f"Lone {Tile(tid).long_name} — keep an eye on a 2nd copy."
            keep = [tid]
        else:
            continue
        out.append(YakuDirection(
            f"yakuhai_{tid}", f"Yakuhai ({Tile(tid).long_name})", "役牌",
            confidence, notes=[note], keep_tile_ids=keep,
        ))
    return out


def _check_honitsu(counts, state, open_melds) -> YakuDirection:
    suit_counts = _suit_counts(counts)
    suit_in_meld = {"m": 0, "p": 9, "s": 18}
    # Determine the dominant numbered suit (m/p/s).
    dom = max(("m", "p", "s"), key=lambda s: suit_counts[s])
    if _meld_breaks_honitsu(open_melds, dom):
        return YakuDirection("honitsu", "Half Flush (Honitsu)", "混一色", 0)
    dom_count = suit_counts[dom]
    honors = suit_counts["z"]
    keep = []
    avoid = []
    suit_base = suit_in_meld[dom]
    for tid in range(27):
        if counts[tid] > 0:
            (keep if suit_base <= tid < suit_base + 9 else avoid).append(tid)
    for tid in range(27, 34):
        if counts[tid] > 0:
            keep.append(tid)

    total = dom_count + honors
    # Confidence rises sharply once the hand is "honitsu shaped".
    if total >= 13:
        confidence = 95
    elif total >= 11:
        confidence = 80
    elif total >= 9:
        confidence = 55
    elif total >= 7:
        confidence = 30
    else:
        confidence = 0
    notes = []
    if confidence >= 70:
        notes.append(
            f"Hand is mostly {dom}-suit + honors — Honitsu within reach (2 han closed)."
        )
    elif confidence >= 30:
        notes.append(f"Possible Honitsu in {dom}-suit if other suits are released.")
    return YakuDirection(
        "honitsu", "Half Flush (Honitsu)", "混一色",
        confidence, notes=notes, keep_tile_ids=keep, avoid_tile_ids=avoid,
    )


def _check_chinitsu(counts, state, open_melds) -> YakuDirection:
    suit_counts = _suit_counts(counts)
    if suit_counts["z"] > 0 or any(
        any(t >= 27 for t in m.tiles) for m in open_melds
    ):
        return YakuDirection("chinitsu", "Full Flush (Chinitsu)", "清一色", 0)
    dom = max(("m", "p", "s"), key=lambda s: suit_counts[s])
    if _meld_breaks_honitsu(open_melds, dom):
        return YakuDirection("chinitsu", "Full Flush (Chinitsu)", "清一色", 0)
    dom_count = suit_counts[dom]
    suit_base = {"m": 0, "p": 9, "s": 18}[dom]
    keep = [t for t in range(suit_base, suit_base + 9) if counts[t] > 0]
    avoid = [t for t in range(27) if counts[t] > 0 and not (suit_base <= t < suit_base + 9)]
    if dom_count >= 13:
        confidence = 95
    elif dom_count >= 11:
        confidence = 75
    elif dom_count >= 9:
        confidence = 45
    else:
        confidence = 0
    notes = []
    if confidence >= 70:
        notes.append(
            f"Hand is almost entirely {dom}-suit — Chinitsu within reach (5/6 han)."
        )
    elif confidence >= 30:
        notes.append(f"Chinitsu possible in {dom}-suit; very high value.")
    return YakuDirection(
        "chinitsu", "Full Flush (Chinitsu)", "清一色",
        confidence, notes=notes, keep_tile_ids=keep, avoid_tile_ids=avoid,
    )


def _check_toitoi(counts, state, open_melds) -> YakuDirection:
    # Toitoi: all triplets/quads + 1 pair. Disqualified by any chi meld.
    if any(m.type == "chi" for m in open_melds):
        return YakuDirection("toitoi", "All Triplets (Toitoi)", "对对和", 0)
    pairs = sum(1 for c in counts if c >= 2)
    triplets = sum(1 for c in counts if c >= 3)
    pon_kan_melds = sum(1 for m in open_melds if m.type in ("pon", "kan", "ankan"))
    blocks = pairs + pon_kan_melds  # rough count of "toitoi blocks"
    if blocks < 3:
        return YakuDirection("toitoi", "All Triplets (Toitoi)", "对对和", 0)
    if blocks >= 5:
        confidence = 80
    elif blocks == 4:
        confidence = 55
    else:
        confidence = 35
    keep = [t for t in range(34) if counts[t] >= 2]
    notes = [
        f"{blocks} pair/triplet blocks already — Toitoi direction (2 han)."
    ]
    return YakuDirection(
        "toitoi", "All Triplets (Toitoi)", "对对和",
        confidence, notes=notes, keep_tile_ids=keep,
    )


def _check_chiitoitsu(counts) -> YakuDirection:
    breakdown = calculate_shanten_breakdown(counts, open_melds_count=0)
    sh = breakdown.chiitoitsu
    if sh > 3:
        return YakuDirection("chiitoitsu", "Seven Pairs (Chiitoitsu)", "七对子", 0)
    confidence = max(20, 95 - 20 * max(0, sh + 1))
    keep = [t for t in range(34) if counts[t] >= 2]
    return YakuDirection(
        "chiitoitsu", "Seven Pairs (Chiitoitsu)", "七对子",
        confidence,
        notes=[f"Chiitoitsu shanten = {sh}; pair-collecting plan is alive."],
        keep_tile_ids=keep,
    )


def _check_kokushi(counts) -> YakuDirection:
    breakdown = calculate_shanten_breakdown(counts, open_melds_count=0)
    sh = breakdown.kokushi
    if sh > 5:
        return YakuDirection("kokushi", "Thirteen Orphans (Kokushi)", "国士无双", 0)
    types = sum(1 for t in YAOCHU_IDS if counts[t] >= 1)
    if types < 8 and sh > 3:
        return YakuDirection("kokushi", "Thirteen Orphans (Kokushi)", "国士无双", 0)
    confidence = max(25, 95 - 18 * max(0, sh + 1))
    keep = [t for t in YAOCHU_IDS if counts[t] >= 1]
    return YakuDirection(
        "kokushi", "Thirteen Orphans (Kokushi)", "国士无双",
        confidence,
        notes=[
            f"Kokushi shanten = {sh}; {types}/13 yaochu types in hand."
        ],
        keep_tile_ids=keep,
    )


def _check_honroutou(counts, state, open_melds) -> YakuDirection:
    # Honroutou requires every tile to be a terminal or honor.
    if any(c > 0 and t not in YAOCHU_IDS for t, c in enumerate(counts)):
        return YakuDirection("honroutou", "All Terminals & Honors (Honroutou)", "混老头", 0)
    return YakuDirection(
        "honroutou", "All Terminals & Honors (Honroutou)", "混老头",
        70,
        notes=["All your tiles are terminals/honors — Honroutou direction."],
        keep_tile_ids=list(YAOCHU_IDS),
    )


# ---------------------------------------------------------------------------
# Value hints + per-tile reasons
# ---------------------------------------------------------------------------


def _value_hints(state, counts) -> dict:
    from .game import dora_tile_for
    dora_tile_ids = [dora_tile_for(t) for t in state.dora_indicators]
    dora_in_hand = 0
    for tid in dora_tile_ids:
        dora_in_hand += counts[tid]
        for m in state.user.melds:
            for t in m.tiles:
                if t == tid:
                    dora_in_hand += 1
    aka_in_hand = total_user_aka(state)
    yakuhai_pairs = []
    for tid in range(27, 34):
        if counts[tid] >= 2 and _is_yakuhai(state, tid):
            yakuhai_pairs.append(tile_code(tid))
    return {
        "dora_in_hand": dora_in_hand,
        "aka_dora_in_hand": aka_in_hand,
        "dora_tile_ids": dora_tile_ids,
        "dora_tile_codes": [tile_code(t) for t in dora_tile_ids],
        "yakuhai_pairs": yakuhai_pairs,
    }


def _per_tile_reasons(directions, state, counts, value_hints) -> Dict[int, List[str]]:
    reasons: Dict[int, List[str]] = {}
    def add(tid: int, key: str):
        reasons.setdefault(tid, [])
        if key not in reasons[tid]:
            reasons[tid].append(key)

    for tid in value_hints["dora_tile_ids"]:
        if counts[tid] > 0:
            add(tid, "dora")
    for code in value_hints["yakuhai_pairs"]:
        # value_hints stores codes; convert back.
        from .tiles import tile_id_from_code
        tid = tile_id_from_code(code)
        add(tid, "yakuhai")

    direction_keep_keys = {
        "tanyao": "keep_tanyao",
        "honitsu": "keep_honitsu",
        "chinitsu": "keep_chinitsu",
        "toitoi": "keep_toitoi",
        "chiitoitsu": "keep_chiitoitsu",
        "kokushi": "keep_kokushi",
        "honroutou": "keep_kokushi",  # piggy-back on kokushi style
    }
    direction_break_keys = {
        "tanyao": "break_tanyao",
        "honitsu": "break_honitsu",
        "chinitsu": "break_chinitsu",
    }
    for d in directions:
        # Yakuhai_<tile> is per-tile; map to "yakuhai" reason on that tile.
        if d.name.startswith("yakuhai_"):
            for tid in d.keep_tile_ids:
                add(tid, "yakuhai")
            continue
        keep_key = direction_keep_keys.get(d.name)
        if keep_key:
            for tid in d.keep_tile_ids:
                add(tid, keep_key)
        break_key = direction_break_keys.get(d.name)
        if break_key:
            for tid in d.avoid_tile_ids:
                add(tid, break_key)
    return reasons
