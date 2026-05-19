"""Phase 1 HTTP API for the tile-efficiency engine.

All endpoints accept the hand as a list of tile codes (preferred) or a
compact mpsz string. The frontend sends a JSON list of tile ids/codes.
"""

from __future__ import annotations

from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..mahjong import (
    GameState,
    Meld,
    NUM_TILES,
    PlayerState,
    Tile,
    analyze_call,
    analyze_game,
    analyze_hand,
    calculate_shanten,
    calculate_ukeire,
    can_user_ankan,
    can_user_open_kan,
    can_user_pon,
    get_legal_chi_options,
    parse_hand,
    tile_code,
    tile_id_from_code,
    user_ankan_candidates,
    validate_tile_pool,
)
from ..mahjong.shanten import calculate_shanten_breakdown


router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class HandRequest(BaseModel):
    """Hand may be given as a list of codes/ids or a compact mpsz string."""

    hand: Union[str, List[Union[str, int]]] = Field(
        ...,
        description="Either an mpsz string ('123m456p789s11122z') or a list of tile codes/ids",
    )


class TileMetadata(BaseModel):
    tile_id: int
    code: str
    short_name: str
    long_name: str
    image: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_counts(payload: HandRequest) -> List[int]:
    counts = [0] * NUM_TILES
    raw = payload.hand
    try:
        if isinstance(raw, str):
            ids = parse_hand(raw)
        else:
            ids = []
            for entry in raw:
                if isinstance(entry, int):
                    ids.append(entry)
                else:
                    ids.append(tile_id_from_code(entry))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for tid in ids:
        if not 0 <= tid < NUM_TILES:
            raise HTTPException(status_code=400, detail=f"tile id out of range: {tid}")
        counts[tid] += 1
        if counts[tid] > 4:
            raise HTTPException(
                status_code=400,
                detail=f"more than 4 copies of tile id {tid} ({tile_code(tid)})",
            )
    return counts


def _validate_size(counts: List[int], allowed: tuple[int, ...]) -> None:
    n = sum(counts)
    if n not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"hand has {n} tiles; expected one of {allowed}",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tiles", response_model=List[TileMetadata])
def list_tiles() -> List[TileMetadata]:
    """List every tile type the engine knows about, with image filename."""
    out: List[TileMetadata] = []
    for tid in range(NUM_TILES):
        t = Tile(tid)
        out.append(
            TileMetadata(
                tile_id=tid,
                code=t.code,
                short_name=t.short_name,
                long_name=t.long_name,
                image=t.image_filename,
            )
        )
    return out


@router.post("/shanten")
def shanten_endpoint(payload: HandRequest) -> dict:
    counts = _to_counts(payload)
    _validate_size(counts, (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14))
    breakdown = calculate_shanten_breakdown(counts)
    return {
        "shanten": breakdown.overall,
        "normal": breakdown.normal,
        "chiitoitsu": breakdown.chiitoitsu,
        "kokushi": breakdown.kokushi,
        "best_form": breakdown.best_form,
    }


@router.post("/ukeire")
def ukeire_endpoint(payload: HandRequest) -> dict:
    counts = _to_counts(payload)
    _validate_size(counts, (13,))
    shanten = calculate_shanten(counts)
    uke = calculate_ukeire(counts, current_shanten=shanten)
    return {
        "shanten": shanten,
        "ukeire": [
            {"tile_id": t, "tile_code": tile_code(t), "remaining": r}
            for t, r in sorted(uke.items())
        ],
        "ukeire_count": sum(uke.values()),
    }


@router.post("/analyze")
def analyze_endpoint(payload: HandRequest) -> dict:
    counts = _to_counts(payload)
    _validate_size(counts, (13, 14))
    return analyze_hand(counts)


# ---------------------------------------------------------------------------
# Phase 2: game-state aware analysis
# ---------------------------------------------------------------------------


class MeldPayload(BaseModel):
    type: str = Field(..., description="One of 'chi', 'pon', 'kan', 'ankan'")
    tiles: List[Union[str, int]]
    called_from: Optional[int] = Field(
        None, description="Seat index (0..3) the call took the tile from"
    )
    aka_count: int = Field(0, description="How many of this meld's tiles are red fives")


class PlayerPayload(BaseModel):
    discards: List[Union[str, int]] = Field(default_factory=list)
    melds: List[MeldPayload] = Field(default_factory=list)
    riichi: bool = False
    riichi_discard_index: Optional[int] = None


class GameStatePayload(BaseModel):
    round_wind: Union[str, int] = "1z"
    seat_wind: Union[str, int] = "1z"
    honba: int = 0
    riichi_sticks: int = 0
    dora_indicators: List[Union[str, int]] = Field(default_factory=list)
    turn_number: int = 0
    hand: List[Union[str, int]] = Field(default_factory=list)
    drawn_tile: Optional[Union[str, int]] = None
    aka_in_hand: int = Field(0, description="Number of red fives in the user's concealed hand")
    user: PlayerPayload = Field(default_factory=PlayerPayload)
    opponents: List[PlayerPayload] = Field(default_factory=lambda: [PlayerPayload(), PlayerPayload(), PlayerPayload()])


def _coerce_tile_id(value: Union[str, int]) -> int:
    if isinstance(value, int):
        if not 0 <= value < NUM_TILES:
            raise HTTPException(status_code=400, detail=f"tile id out of range: {value}")
        return value
    try:
        return tile_id_from_code(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _coerce_tile_list(values: List[Union[str, int]]) -> List[int]:
    return [_coerce_tile_id(v) for v in values]


def _coerce_player(payload: PlayerPayload) -> PlayerState:
    melds = [
        Meld(
            type=m.type,
            tiles=_coerce_tile_list(m.tiles),
            called_from=m.called_from,
            aka_count=m.aka_count,
        )
        for m in payload.melds
    ]
    return PlayerState(
        discards=_coerce_tile_list(payload.discards),
        melds=melds,
        riichi=payload.riichi,
        riichi_discard_index=payload.riichi_discard_index,
    )


def _coerce_state(payload: GameStatePayload) -> GameState:
    if len(payload.opponents) != 3:
        raise HTTPException(status_code=400, detail="opponents must have length 3")
    try:
        return GameState(
            round_wind=_coerce_tile_id(payload.round_wind),
            seat_wind=_coerce_tile_id(payload.seat_wind),
            honba=payload.honba,
            riichi_sticks=payload.riichi_sticks,
            dora_indicators=_coerce_tile_list(payload.dora_indicators),
            turn_number=payload.turn_number,
            hand=_coerce_tile_list(payload.hand),
            drawn_tile=_coerce_tile_id(payload.drawn_tile) if payload.drawn_tile is not None else None,
            aka_in_hand=payload.aka_in_hand,
            user=_coerce_player(payload.user),
            opponents=[_coerce_player(op) for op in payload.opponents],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze-game")
def analyze_game_endpoint(payload: GameStatePayload) -> dict:
    """Full analysis with defense given a complete game-state snapshot.

    Closed hand size may be 13 or 14 with no open melds, or any of
    ``13 - 3K`` / ``14 - 3K`` once K open melds are recorded. The detailed
    validation lives inside :func:`analyze_game`.

    Before doing any analysis we run :func:`validate_tile_pool`. If the
    snapshot is structurally impossible (e.g. 5 copies of the same tile,
    2 red 5m visible in melds) we return 400 instead of producing a
    nonsense answer; the frontend then rolls back the offending action.
    """
    state = _coerce_state(payload)
    pool_errors = validate_tile_pool(state)
    if pool_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "tile_pool_invalid",
                "messages": pool_errors,
            },
        )
    try:
        return analyze_game(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Call-opportunity analysis (Phase 2.5)
# ---------------------------------------------------------------------------


class CallAnalysisRequest(BaseModel):
    state: GameStatePayload
    discarded_tile: Union[str, int]
    discarder_seat: int = Field(..., ge=0, le=3)


@router.post("/analyze-call")
def analyze_call_endpoint(payload: CallAnalysisRequest) -> dict:
    """Given a discard, return the user's chi/pon/kan/ron options with notes."""
    state = _coerce_state(payload.state)
    pool_errors = validate_tile_pool(state)
    if pool_errors:
        raise HTTPException(
            status_code=400,
            detail={"error": "tile_pool_invalid", "messages": pool_errors},
        )
    tile_id = _coerce_tile_id(payload.discarded_tile)
    try:
        return analyze_call(state, tile_id, payload.discarder_seat)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Legality endpoint — used by the frontend to disable illegal drop zones
# ---------------------------------------------------------------------------


class LegalityRequest(BaseModel):
    state: GameStatePayload
    discarded_tile: Optional[Union[str, int]] = None
    discarder_seat: Optional[int] = Field(None, ge=0, le=3)


@router.post("/legality")
def legality_endpoint(payload: LegalityRequest) -> dict:
    """Return the user's strict legality matrix for the latest discard.

    ``discarded_tile`` and ``discarder_seat`` may be omitted — in that
    case only ankan candidates are returned (the only call that does not
    depend on someone else's discard).
    """
    state = _coerce_state(payload.state)
    pool_errors = validate_tile_pool(state)
    response = {
        "tile_pool_valid": len(pool_errors) == 0,
        "tile_pool_errors": pool_errors,
        "ankan_candidates": user_ankan_candidates(state),
    }
    if payload.discarded_tile is None or payload.discarder_seat is None:
        response.update(
            {
                "discarded_tile_id": None,
                "discarder_seat": None,
                "can_pon": False,
                "can_kan": False,
                "chi_options": [],
            }
        )
        return response
    tile_id = _coerce_tile_id(payload.discarded_tile)
    response.update(
        {
            "discarded_tile_id": tile_id,
            "discarder_seat": payload.discarder_seat,
            "can_pon": can_user_pon(state, tile_id),
            "can_kan": can_user_open_kan(state, tile_id),
            "chi_options": [
                list(pair)
                for pair in get_legal_chi_options(
                    state, tile_id, payload.discarder_seat, caller_seat=0
                )
            ],
        }
    )
    return response
