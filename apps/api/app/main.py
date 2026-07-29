"""FastAPI application factory.

This module wires the application together and nothing else: no business
logic, no data access. Routers live under ``app.api``, domain rules under
``app.engines``.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.routers import conflicts, health, kb, me, projects, variants
from app.core import problem_details
from app.core.config import Settings, get_settings
from app.core.limits import RequestSizeLimitMiddleware
from app.core.request_context import REQUEST_ID_HEADER, RequestIdMiddleware
from app.core.security import build_verifier
from app.db.supabase import build_client
from app.services.groq_client import GroqClient

#: Mounted under ``/v1`` rather than ``/api/v1``: this service serves nothing
#: but the API, so the extra segment would name the only thing there is.
API_V1_PREFIX = "/v1"


def create_app(
    settings: Settings | None = None,
    *,
    auth_transport: httpx.AsyncBaseTransport | None = None,
    db_transport: httpx.AsyncBaseTransport | None = None,
    groq_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build and configure the ASGI application.

    The three transports are injected only by tests, which drive the JWKS
    fetch, PostgREST and Groq through ``httpx.MockTransport`` so no test
    reaches the network. In production every one of them is ``None`` and httpx
    uses its own.
    """
    settings = settings or get_settings()

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

    app.state.settings = settings
    app.state.token_verifier = build_verifier(settings, transport=auth_transport)
    app.state.supabase = build_client(settings, transport=db_transport)
    app.state.groq = GroqClient(settings=settings, transport=groq_transport)

    # Middleware runs outermost-first in reverse registration order, so the
    # request id is bound before CORS and before anything that might log.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
    )
    app.add_middleware(RequestIdMiddleware)
    # Registered last, so it runs first: an oversized body is refused before
    # anything else touches it, including the request-id middleware.
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)

    problem_details.install(app)

    app.include_router(health.router)
    for router in (me.router, kb.router, conflicts.router, projects.router, variants.router):
        app.include_router(router, prefix=API_V1_PREFIX)

    return app


app = create_app()
