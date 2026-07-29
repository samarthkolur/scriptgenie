"""Building an application whose every outbound call is a mock transport.

Three transports and no network: the JWKS server, PostgREST, and Groq. A test
that reached any of them would be slow, flaky, and would spend a real token
allowance to assert something about routing.

The Groq stub is scripted per call rather than returning one canned reply,
because generation makes N concurrent variant calls followed by N verification
extractions, and a stub that answered them all identically could not tell a
partial batch from a complete one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient

from app.main import API_V1_PREFIX, create_app
from tests.auth_fixtures import JwksServer, PostgrestStub, SigningKey, claims, settings

#: The worked example from the research: horror-comedy, PG-13, micro budget,
#: released in the US and India. It produces three conflicts at known
#: severities, which is what makes it useful for asserting the gate.
WORKED_EXAMPLE: dict[str, Any] = {
    "genre": {"primary": "horror", "secondary": "comedy"},
    "audience": {"min_age": 15, "max_age": 40},
    "rating": {"system": "mpa", "classification": "pg_13"},
    "budget_tier_id": "micro",
    "territories": {"ids": ["us", "india"]},
}

#: A bundle with no tension in it: a contemporary drama at a tier that can
#: afford it, one territory, an audience the rating admits.
CLEAN_BUNDLE: dict[str, Any] = {
    "genre": {"primary": "drama"},
    "audience": {"min_age": 18, "max_age": 60},
    "rating": {"system": "mpa", "classification": "r"},
    "budget_tier_id": "studio",
    "territories": {"ids": ["us"]},
}

PROJECT_ID = UUID("aaaaaaaa-0000-4000-8000-000000000001")
OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")


def project_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": str(PROJECT_ID),
        "owner_id": str(OWNER_ID),
        "title": "Cabin horror comedy",
        "description": None,
        "status": "draft",
        "created_at": "2026-07-29T09:00:00+00:00",
        "updated_at": "2026-07-29T09:00:00+00:00",
    }
    row.update(overrides)
    return row


def stored_row(table: str, **overrides: Any) -> dict[str, Any]:
    """A generic inserted row: an id and whatever the caller cares about."""
    row: dict[str, Any] = {
        "id": str(uuid4()),
        "owner_id": str(OWNER_ID),
        "project_id": str(PROJECT_ID),
        "created_at": "2026-07-29T09:00:00+00:00",
        "table": table,
    }
    row.update(overrides)
    return row


def run_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": str(uuid4()),
        "project_id": str(PROJECT_ID),
        "owner_id": str(OWNER_ID),
        "status": "running",
        "requested_count": 2,
        "generated_count": 0,
        "failed_count": 0,
        "seed": 0,
        "model": "openai/gpt-oss-120b",
        "prompt_version": "1.0.0",
        "kb_version": "0.1.1",
        "elapsed_ms": None,
        "created_at": "2026-07-29T09:00:00+00:00",
        "completed_at": None,
    }
    row.update(overrides)
    return row


def variant_row(index: int = 0, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": str(uuid4()),
        "run_id": str(uuid4()),
        "project_id": str(PROJECT_ID),
        "owner_id": str(OWNER_ID),
        "variant_index": index,
        "archetype_id": "crucible",
        "title": f"Variant {index}",
        "logline": "Five friends cannot leave the cabin until they admit what they did.",
        "beats": [
            {"index": 0, "function": "setup", "summary": "They arrive at the cabin."},
            {"index": 1, "function": "turn", "summary": "The road out is gone."},
        ],
        "locations": ["cabin interior", "porch"],
        "named_characters": ["Mara", "Deb", "Tom"],
        "relaxations": [],
        "satisfaction": {
            "dimension_checks": [
                {"dimension": "violence", "permitted": 2, "observed": 1, "satisfied": True}
            ],
            "scope_checks": [
                {"parameter": "max_locations", "limit": 3, "observed": 2, "satisfied": True}
            ],
            "satisfied": True,
            "violations": [],
        },
        "verdicts": {"max_locations": "PASS", "violence": "PASS"},
        "surfaceable": True,
        "favourite": False,
        "notes": None,
        "provenance": {
            "kb_version": "0.1.1",
            "prompt_version": "1.0.0",
            "model": "openai/gpt-oss-120b",
            "archetype_id": "crucible",
            "seed": 0,
            "attempts": 1,
            "repaired": False,
        },
        "created_at": "2026-07-29T09:00:00+00:00",
    }
    row.update(overrides)
    return row


@dataclass
class GroqStub:
    """A Groq that answers variant calls and extraction calls differently.

    They are told apart by the request payload: an extraction asks for the six
    content dimensions, a variant asks for beats. A stub that could not tell
    them apart would make a "verified" variant indistinguishable from one whose
    verification never ran, which is the exact distinction the verifier exists
    to preserve.
    """

    variants: list[dict[str, Any]] = field(default_factory=list)
    #: Content levels the extraction reports, or ``None`` to fail extraction and
    #: force every content axis to NEEDS_REVIEW.
    extraction: dict[str, int] | None = None
    variant_status: int = 200
    calls: list[dict[str, Any]] = field(default_factory=list)
    _next_variant: int = field(default=0, init=False)

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.calls.append(payload)
            schema = payload["response_format"].get("json_schema", {}).get("schema", {})
            properties = set(schema.get("properties", {}))

            if "violence" in properties:
                if self.extraction is None:
                    return httpx.Response(500, json={"error": {"message": "extractor down"}})
                return self._completion(self.extraction)

            if self.variant_status != 200:
                return httpx.Response(
                    self.variant_status, json={"error": {"message": "model unavailable"}}
                )

            index = min(self._next_variant, len(self.variants) - 1)
            self._next_variant += 1
            return self._completion(self.variants[index])

        return httpx.MockTransport(handler)

    def _completion(self, content: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-120b",
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 800, "completion_tokens": 400},
            },
        )


def variant_payload(title: str = "The Locked Cabin", locations: int = 2) -> dict[str, Any]:
    """A model reply that satisfies the output contract."""
    return {
        "title": title,
        "logline": "Five friends cannot leave the cabin until they admit what they did.",
        "beats": [
            {"function": "setup", "summary": "They arrive for a reunion weekend."},
            {"function": "inciting", "summary": "The road out has washed away."},
            {"function": "escalation", "summary": "Someone admits to the old lie."},
            {"function": "crisis", "summary": "The group turns on itself."},
            {"function": "resolution", "summary": "They walk out at dawn, changed."},
        ],
        "locations": [f"location {n}" for n in range(locations)],
        "named_characters": ["Mara", "Deb", "Tom"],
        "relaxations": [],
        "satisfaction": {},
    }


CLEAN_EXTRACTION = {
    "violence": 0,
    "sexual_content": 0,
    "language": 0,
    "thematic_darkness": 1,
    "drug_use": 0,
    "horror_intensity": 1,
}


@dataclass
class ApiHarness:
    """An application, a valid token, and the stubs behind it."""

    client: TestClient
    token: str
    db: PostgrestStub
    groq: GroqStub

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.get(f"{API_V1_PREFIX}{path}", headers=self._auth(), **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.post(f"{API_V1_PREFIX}{path}", headers=self._auth(), **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.patch(f"{API_V1_PREFIX}{path}", headers=self._auth(), **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.client.delete(f"{API_V1_PREFIX}{path}", headers=self._auth(), **kwargs)

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def harness(
    db: PostgrestStub | None = None,
    groq: GroqStub | None = None,
    **setting_overrides: Any,
) -> ApiHarness:
    key = SigningKey.generate("key-1")
    postgrest = db or PostgrestStub()
    groq_stub = groq or GroqStub(variants=[variant_payload()], extraction=CLEAN_EXTRACTION)

    app = create_app(
        settings(groq_api_key="test-key-not-a-real-credential", **setting_overrides),
        auth_transport=JwksServer([key]).transport(),
        db_transport=postgrest.transport(),
        groq_transport=groq_stub.transport(),
    )
    return ApiHarness(
        client=TestClient(app),
        token=key.sign(claims(subject=OWNER_ID)),
        db=postgrest,
        groq=groq_stub,
    )
