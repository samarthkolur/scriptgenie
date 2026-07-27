"""Liveness endpoint.

Deliberately unauthenticated and dependency-free: it answers whether this
process is up, and reports the versions that determine its behaviour.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import Environment, get_settings
from app.kb.loader import get_knowledge_base

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Service liveness and version information.

    ``kb_version`` is reported because the knowledge base determines every
    conflict verdict this service produces. Knowing the service version
    without it would not identify the behaviour being observed.
    """

    status: str
    version: str
    kb_version: str
    environment: Environment


@router.get("/health", response_model=HealthResponse, summary="Service liveness")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        kb_version=get_knowledge_base().version,
        environment=settings.app_env,
    )
