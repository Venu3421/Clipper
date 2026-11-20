import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    BASE_DIR,
    ensure_directories,
    FFMPEG_PATH,
    FFPROBE_PATH,
)
from app.api.routes import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("clipstream")

# Ensure required directories exist
ensure_directories()

app = FastAPI(
    title="ClipStream AI",
    description="Local Viral Shorts & Live Stream Studio",
    version="1.0.0"
)

# CORS middleware
# Local-only app: restrict to the dashboard origin. allow_credentials is dropped
# because "*" + credentials is invalid per the CORS spec and browsers drop the headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Gate every /api/* request behind an API token.

    Set CLIPSTREAM_API_TOKEN in your environment (or .env). The dashboard
    ("/", "/static", "/media") is never gated.

    A JSONResponse is returned directly instead of raising HTTPException so
    that Starlette's ServerErrorMiddleware does not intercept and re-raise it
    (it always re-raises HTTPException, which breaks test clients).
    """
    if request.url.path.startswith("/api"):
        expected = os.getenv("CLIPSTREAM_API_TOKEN", "").strip()
        if not expected:
            return JSONResponse(
                status_code=503,
                content={"detail": "Server misconfiguration: CLIPSTREAM_API_TOKEN is not set."},
            )
        provided = request.headers.get("X-API-Key", "").strip()
        if not provided or provided != expected:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )
    return await call_next(request)


@app.exception_handler(Exception)
async def handle_unexpected_errors(request: Request, exc: Exception):
    """Catch-all so internal errors never leak stack traces to the client."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


# Static files & templates
static_dir = BASE_DIR / "app" / "web" / "static"
templates_dir = BASE_DIR / "app" / "web" / "templates"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# Include API Router
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Serve the main studio dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.on_event("startup")
async def on_startup():
    logger.info("=" * 60)
    logger.info("ClipStream AI - Viral Shorts & Live Stream Studio")
    logger.info(f"FFmpeg Path : {FFMPEG_PATH or 'NOT FOUND'}")
    logger.info(f"FFprobe Path: {FFPROBE_PATH or 'NOT FOUND'}")
    logger.info("Open http://localhost:8000 in your browser.")
    logger.info("=" * 60)
