"""FastAPI entry point for the associative analytics engine."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.chat_routes import router as chat_router
from app.api.llm_routes import router as llm_router
from app.api.data_routes import router as data_router
from app.api.object_routes import router as object_router
from app.api.dashboard_routes import router as dashboard_router
from app.api.conversation_routes import router as conversation_router
from app.api.onboarding_routes import router as onboarding_router
from app.api.extraction_routes import router as extraction_router
from app.api.mcp_routes import router as mcp_router
from app.spaces.routes import router as spaces_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init SQLite
    from app.store import init_db
    await init_db()

    # Startup: load saved data spaces
    try:
        from app.spaces.registry import load_saved_spaces
        load_saved_spaces()
    except Exception as e:
        log.warning(f"Failed to load saved data spaces: {e}")

    # Startup: auto-discover customer config from silver if not already populated.
    # Only fills keys still at their default — never overwrites operator choices.
    try:
        from app.customer import config as customer_config
        from app.db import get_client
        cfg = customer_config.load()
        discovered = customer_config.auto_discover(get_client())
        if discovered:
            merged = customer_config.merge_defaults_only(cfg, discovered)
            if merged != cfg:
                customer_config.save(merged)
                log.info("Auto-discovered customer config from silver: %s", sorted(set(merged) - set(k for k in merged if cfg.get(k) == merged[k])))
    except Exception as e:
        log.warning(f"Customer config auto-discover skipped: {e}")

    # Log extraction summary so operators can sanity-check the enabled set
    try:
        from app.customer import extraction
        log.info(extraction.summary())
    except Exception as e:
        log.warning(f"Extraction summary skipped: {e}")
    yield


app = FastAPI(
    title="HubSpot Analytics Engine",
    description="Qlik-like associative model on ClickHouse",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — locked to localhost origins by default since ClickSpot is self-hosted.
# Override via CLICKSPOT_CORS_ORIGINS env (comma-separated) for VPN / reverse-proxy setups.
# DO NOT set this to "*" — combined with the no-auth model that lets any website on
# the internet POST queries to your local instance.
import os as _os
_default_origins = ",".join([
    "http://localhost:8193",   # Vite dev server (frontend)
    "http://127.0.0.1:8193",
    "http://localhost:8192",   # FastAPI itself (e.g. /docs swagger)
    "http://127.0.0.1:8192",
])
_cors_origins = [
    o.strip() for o in _os.environ.get("CLICKSPOT_CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["content-type", "authorization"],
)

app.include_router(router)
app.include_router(chat_router)
app.include_router(llm_router)
app.include_router(data_router)
app.include_router(object_router)
app.include_router(dashboard_router)
app.include_router(conversation_router)
app.include_router(onboarding_router)
app.include_router(extraction_router)
app.include_router(mcp_router)
app.include_router(spaces_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Optional: serve the built frontend from FastAPI itself.
# When CLICKSPOT_STATIC_DIR points at a Vite `dist/`, the SPA is served on the
# same origin as the API. This is what the all-in-one preloaded demo image uses
# (it has no nginx). The compose stack leaves it unset — nginx serves the
# frontend there — so /docs and the OpenAPI routes keep their normal behaviour.
# ---------------------------------------------------------------------------
_static_dir = _os.environ.get("CLICKSPOT_STATIC_DIR")
if _static_dir and _os.path.isdir(_static_dir):
    from fastapi.responses import FileResponse

    _static_root = _os.path.abspath(_static_dir)
    _index_file = _os.path.join(_static_root, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # The API routers and /health are registered above and match first, so
        # this only sees asset requests and client-side routes. Serve the real
        # file when it exists (guarding against path traversal); otherwise fall
        # back to index.html so deep links resolve in the SPA.
        candidate = _os.path.normpath(_os.path.join(_static_root, full_path))
        if full_path and candidate.startswith(_static_root) and _os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_index_file)

    log.info("Serving static frontend from %s", _static_root)
