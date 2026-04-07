"""FastAPI entry point for the associative analytics engine."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.chat_routes import router as chat_router
from app.api.data_routes import router as data_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="HubSpot Analytics Engine",
    description="Qlik-like associative model on ClickHouse",
    version="0.1.0",
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


@app.get("/health")
def health():
    return {"status": "ok"}
