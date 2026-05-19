"""Browser bridge: the FastAPI route logic, minus FastAPI.

GitHub Pages can only serve static files, so the engine runs *in the
browser* via Pyodide. This module re-implements exactly what
``backend/app/api/routes.py`` does (payload coercion, tile-pool
validation, error shapes) but as plain functions that take/return JSON,
with **no** ``fastapi`` / ``pydantic`` import — Pyodide loads only the
pure-Python ``app.mahjong`` package plus this file.

``backend/tests/test_web_bridge.py`` asserts these functions return
byte-identical bodies to the live API for representative inputs, so the
static site and the server can never silently diverge.
"""

from __future__ import annotations

import json
from typing import Any, List, Union

from .mahjong import (
    GameState,
    Meld,
    NUM_TILES,
    PlayerState,
    Tile,
    analyze_call,
    analyze_game,
    analyze_hand,
    parse_hand,
    tile_code,
    tile_id_from_code,
    validate_tile_pool,
)


class BridgeError(Exception):
    """Mirrors a FastAPI ``HTTPException`` — carries an HTTP-ish status
    and a ``detail`` that is either a string or the structured pool-error
    object the frontend already knows how to read."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


# ---------------------------------------------------------------------------
# Coercion helpers (ported verbatim from api/routes.py)
# ---------------------------------------------------------------------------


def _to_counts(hand: Union[str, List[Union[str, int]]]) -> List[int]:
    counts = [0] * NUM_TILES
    try:
        if isinstance(hand, str):
            ids = parse_hand(hand)
        else:
            ids = []
            for entry in hand:
                if isinstance(entry, int):
                    ids.append(entry)
                else:
                    ids.append(tile_id_from_code(entry))
    except ValueError as exc:
        raise BridgeError(400, str(exc)) from exc

    for tid in ids:
        if not 0 <= tid < NUM_TILES:
            raise BridgeError(400, f"tile id out of range: {tid}")
        counts[tid] += 1
        if counts[tid] > 4:
            raise BridgeError(
                400, f"more than 4 copies of tile id {tid} ({tile_code(tid)})"
            )
    return counts


def _validate_size(counts: List[int], allowed: tuple) -> None:
    n = sum(counts)
    if n not in allowed:
        raise BridgeError(400, f"hand has {n} tiles; expected one of {allowed}")


def _coerce_tile_id(value: Union[str, int]) -> int:
    if isinstance(value, int):
        if not 0 <= value < NUM_TILES:
            raise BridgeError(400, f"tile id out of range: {value}")
        return value
    try:
        return tile_id_from_code(str(value))
    except ValueError as exc:
        raise BridgeError(400, str(exc)) from exc


def _coerce_tile_list(values: List[Union[str, int]]) -> List[int]:
    return [_coerce_tile_id(v) for v in values]


def _coerce_player(p: dict) -> PlayerState:
    melds = [
        Meld(
            type=m["type"],
            tiles=_coerce_tile_list(m.get("tiles", [])),
            called_from=m.get("called_from"),
            aka_count=m.get("aka_count", 0),
        )
        for m in p.get("melds", [])
    ]
    return PlayerState(
        discards=_coerce_tile_list(p.get("discards", [])),
        melds=melds,
        riichi=bool(p.get("riichi", False)),
        riichi_discard_index=p.get("riichi_discard_index"),
    )


def _coerce_state(payload: dict) -> GameState:
    opponents = payload.get("opponents") or [{}, {}, {}]
    if len(opponents) != 3:
        raise BridgeError(400, "opponents must have length 3")
    user = payload.get("user") or {}
    drawn = payload.get("drawn_tile")
    try:
        return GameState(
            round_wind=_coerce_tile_id(payload.get("round_wind", "1z")),
            seat_wind=_coerce_tile_id(payload.get("seat_wind", "1z")),
            honba=payload.get("honba", 0),
            riichi_sticks=payload.get("riichi_sticks", 0),
            dora_indicators=_coerce_tile_list(payload.get("dora_indicators", [])),
            turn_number=payload.get("turn_number", 0),
            hand=_coerce_tile_list(payload.get("hand", [])),
            drawn_tile=_coerce_tile_id(drawn) if drawn is not None else None,
            aka_in_hand=payload.get("aka_in_hand", 0),
            user=_coerce_player(user),
            opponents=[_coerce_player(op) for op in opponents],
        )
    except ValueError as exc:
        raise BridgeError(400, str(exc)) from exc


# ---------------------------------------------------------------------------
# Endpoint equivalents
# ---------------------------------------------------------------------------


def list_tiles() -> list:
    out = []
    for tid in range(NUM_TILES):
        t = Tile(tid)
        out.append(
            {
                "tile_id": tid,
                "code": t.code,
                "short_name": t.short_name,
                "long_name": t.long_name,
                "image": t.image_filename,
            }
        )
    return out


def analyze(payload: dict) -> dict:
    counts = _to_counts(payload["hand"])
    _validate_size(counts, (13, 14))
    return analyze_hand(counts)


def analyze_game_payload(payload: dict) -> dict:
    state = _coerce_state(payload)
    pool_errors = validate_tile_pool(state)
    if pool_errors:
        raise BridgeError(
            400, {"error": "tile_pool_invalid", "messages": pool_errors}
        )
    try:
        return analyze_game(state)
    except ValueError as exc:
        raise BridgeError(400, str(exc)) from exc


def analyze_call_payload(payload: dict) -> dict:
    state = _coerce_state(payload["state"])
    pool_errors = validate_tile_pool(state)
    if pool_errors:
        raise BridgeError(
            400, {"error": "tile_pool_invalid", "messages": pool_errors}
        )
    tile_id = _coerce_tile_id(payload["discarded_tile"])
    seat = payload["discarder_seat"]
    if not isinstance(seat, int) or not 0 <= seat <= 3:
        raise BridgeError(400, "discarder_seat must be 0..3")
    try:
        return analyze_call(state, tile_id, seat)
    except ValueError as exc:
        raise BridgeError(400, str(exc)) from exc


# ---------------------------------------------------------------------------
# JSON string entry points (what the Pyodide layer actually calls).
#
# Always returns a JSON string of either ``{"ok": true, "data": ...}`` or
# ``{"ok": false, "status": N, "detail": ...}`` so the JS side never has
# to marshal Python exceptions across the boundary.
# ---------------------------------------------------------------------------


def _run(fn, *args) -> str:
    try:
        return json.dumps({"ok": True, "data": fn(*args)})
    except BridgeError as e:
        return json.dumps({"ok": False, "status": e.status, "detail": e.detail})
    except Exception as e:  # pragma: no cover - last-resort guard
        return json.dumps({"ok": False, "status": 500, "detail": str(e)})


def tiles_json() -> str:
    return _run(list_tiles)


def analyze_json(payload_json: str) -> str:
    return _run(lambda: analyze(json.loads(payload_json)))


def analyze_game_json(payload_json: str) -> str:
    return _run(lambda: analyze_game_payload(json.loads(payload_json)))


def analyze_call_json(payload_json: str) -> str:
    return _run(lambda: analyze_call_payload(json.loads(payload_json)))
