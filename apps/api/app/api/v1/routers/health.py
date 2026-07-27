"""Liveness endpoint.

Deliberately unauthenticated and dependency-free: it answers whether this
process is up, and reports the versions that determine its behaviour.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import Environment, get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Service liveness and version information."""

    status: str
    version: str
    environment: Environment


@router.get("/health", response_model=HealthResponse, summary="Service liveness")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.app_env,
    )
