"""FastAPI application: API + static frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router as api_router


# Project layout: backend/app/main.py  ->  project root is two levels up.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIR = _PROJECT_ROOT / "frontend" / "static"
_TILE_DIR = _FRONTEND_DIR / "tiles"


def create_app() -> FastAPI:
    app = FastAPI(
        title="MahjongAiScreen",
        description="Phase 1: tile efficiency engine + visual hand-input UI.",
        version="0.1.0",
    )

    # Allow the UI to call the API even if it's served from a different origin
    # during development (e.g. running a separate static server).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    # Serve tile assets if they have been downloaded.
    if _TILE_DIR.exists():
        app.mount("/tiles", StaticFiles(directory=_TILE_DIR), name="tiles")

    if _FRONTEND_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=_FRONTEND_DIR, html=False),
            name="static",
        )

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(_FRONTEND_DIR / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def index_missing() -> dict:
            return {
                "message": "Frontend assets are missing.",
                "expected_at": str(_FRONTEND_DIR),
            }

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok", "tiles_present": _TILE_DIR.exists()}

    return app


app = create_app()
