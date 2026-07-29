"""Minting the access tokens the auth tests verify, and serving a JWKS.

A real Supabase project is never contacted. Keys are generated in-process, the
JWKS is served by an ``httpx.MockTransport``, and tokens are signed here — so
these tests exercise the same code paths a deployment uses without a network,
a project, or a credential in the repository.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import Settings

SUPABASE_URL = "https://project.supabase.test"
ISSUER = f"{SUPABASE_URL}/auth/v1"
JWKS_PATH = "/auth/v1/.well-known/jwks.json"


@dataclass
class SigningKey:
    """One EC key, and the JWK the project would publish for it."""

    kid: str
    private_key: ec.EllipticCurvePrivateKey

    @classmethod
    def generate(cls, kid: str) -> SigningKey:
        return cls(kid=kid, private_key=ec.generate_private_key(ec.SECP256R1()))

    def public_jwk(self) -> dict[str, Any]:
        jwk = json.loads(
            jwt.algorithms.ECAlgorithm.to_jwk(self.private_key.public_key())  # type: ignore[no-untyped-call]
        )
        jwk.update({"kid": self.kid, "use": "sig", "alg": "ES256"})
        return jwk

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.private_key, algorithm="ES256", headers={"kid": self.kid})


def claims(
    *,
    subject: UUID | None = None,
    issuer: str = ISSUER,
    audience: str = "authenticated",
    role: str = "authenticated",
    email: str | None = "writer@example.test",
    expires_in: int = 3600,
) -> dict[str, Any]:
    """A Supabase access token's payload, with every claim overridable.

    Every field a test might need to corrupt is a parameter, so a negative case
    changes exactly one thing and the assertion is about that one thing.
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(subject or uuid4()),
        "aud": audience,
        "iss": issuer,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }
    if email is not None:
        payload["email"] = email
    return payload


@dataclass
class JwksServer:
    """A mock transport serving one key set, counting how often it is asked.

    The counter is the point of several tests: the cache must not refetch on
    every request, and an unknown key id must not be able to make it.
    """

    keys: list[SigningKey]
    fetches: int = 0
    status_code: int = 200
    body: dict[str, Any] | None = None
    _failures_remaining: int = field(default=0, init=False)

    def fail_next(self, count: int) -> None:
        self._failures_remaining = count

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fetches += 1
            if self._failures_remaining > 0:
                self._failures_remaining -= 1
                return httpx.Response(503, json={"error": "unavailable"})
            if self.body is not None:
                return httpx.Response(self.status_code, json=self.body)
            return httpx.Response(
                self.status_code, json={"keys": [key.public_jwk() for key in self.keys]}
            )

        return httpx.MockTransport(handler)


@dataclass
class PostgrestStub:
    """A scripted PostgREST, recording what was asked and of whom.

    Responses are keyed by ``METHOD /table`` and consumed in order, so a test
    that expects two calls has to describe both. ``requests`` keeps every
    request so a test can assert on the filters and — more importantly — on
    which credential the call travelled under.
    """

    responses: dict[str, list[httpx.Response]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, table: str, response: httpx.Response) -> PostgrestStub:
        self.responses.setdefault(f"{method.upper()} {table}", []).append(response)
        return self

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            table = request.url.path.rsplit("/", 1)[-1]
            queued = self.responses.get(f"{request.method} {table}")
            if not queued:
                # Louder than a default 200. An unexpected call is a route
                # touching a table the test did not sanction, which is exactly
                # what these tests exist to notice.
                return httpx.Response(
                    500,
                    json={"message": f"no stubbed response for {request.method} {table}"},
                )
            return queued.pop(0)

        return httpx.MockTransport(handler)

    def last(self, method: str, table: str) -> httpx.Request:
        for request in reversed(self.requests):
            if request.method == method.upper() and request.url.path.endswith(f"/{table}"):
                return request
        raise AssertionError(f"no {method} request to {table} was made")


def settings(**overrides: Any) -> Settings:
    """Settings pointed at the fake project.

    ``_env_file=None`` so a developer's local ``.env`` cannot change what these
    tests verify; the values here are the whole configuration under test.
    """
    values: dict[str, Any] = {
        "app_env": "test",
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": "anon-key-for-tests",
        "supabase_service_role_key": "service-role-key-for-tests",
        "supabase_jwks_cache_seconds": 600.0,
        "supabase_jwks_min_refresh_seconds": 30.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)
