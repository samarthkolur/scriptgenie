"""FastAPI application factory.

This module wires the application together and nothing else: no business
logic, no data access. Routers live under ``app.api``, domain rules under
``app.engines``.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.routers import health
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the ASGI application."""
    settings = get_settings()

    app = FastAPI(
        title="ScriptGenie API",
        description=(
            "Constraint-Aware Script Ideation Engine — deterministic constraint "
            "reasoning and archetype-forced plot variant generation."
        ),
        version=__version__,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    )

    app.include_router(health.router)

    return app


app = create_app()
