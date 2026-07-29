"""Shared route dependencies.

Everything a router needs that it should not construct itself. The knowledge
base, the database client and the Groq client are all process-wide and all
expensive to build; a router that instantiated its own would give one request a
different knowledge base version from the next.

Each resolves from ``app.state``, which the factory populates once at startup.
That is what lets a test build an application with mocked transports and have
every route use them without patching a module global.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.db.supabase import SupabaseClient
from app.kb.loader import KnowledgeBase, get_knowledge_base
from app.services.groq_client import GroqClient


def get_kb() -> KnowledgeBase:
    """The process-wide knowledge base.

    Loaded and validated once. Every conflict verdict a running service issues
    comes from this object, which is why ``/health`` reports its version.
    """
    return get_knowledge_base()


def get_app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:  # pragma: no cover - create_app always installs one
        return get_settings()
    assert isinstance(settings, Settings)
    return settings


def get_db(request: Request) -> SupabaseClient:
    client = getattr(request.app.state, "supabase", None)
    if client is None:  # pragma: no cover - create_app always installs one
        raise ConfigurationError("no database client is installed on this application")
    assert isinstance(client, SupabaseClient)
    return client


def get_groq(request: Request) -> GroqClient:
    client = getattr(request.app.state, "groq", None)
    if client is None:  # pragma: no cover - create_app always installs one
        raise ConfigurationError("no language model client is installed on this application")
    assert isinstance(client, GroqClient)
    return client


Kb = Annotated[KnowledgeBase, Depends(get_kb)]
Db = Annotated[SupabaseClient, Depends(get_db)]
Groq = Annotated[GroqClient, Depends(get_groq)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
