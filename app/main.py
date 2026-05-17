"""FastAPI entry point for the associative analytics engine."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.chat_routes import router as chat_router
from app.api.data_routes import router as data_router
from app.api.object_routes import router as object_router
from app.api.dashboard_routes import router as dashboard_router
from app.api.conversation_routes import router as conversation_router
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
    yield


app = FastAPI(
    title="HubSpot Analytics Engine",
    description="Qlik-like associative model on ClickHouse",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(chat_router)
app.include_router(data_router)
app.include_router(object_router)
app.include_router(dashboard_router)
app.include_router(conversation_router)
app.include_router(spaces_router)


@app.get("/health")
def health():
    return {"status": "ok"}
