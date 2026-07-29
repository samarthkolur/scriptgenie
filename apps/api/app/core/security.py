"""Verifying Supabase access tokens, and turning one into a caller.

Every authenticated route depends on :func:`get_current_user`, and everything
that route then does against the database is done with the *caller's own token*
rather than the service role. That is the point of verifying here: the token is
not only a claim about who is asking, it is the credential the database will
re-check on every statement. A forged or expired token must therefore never get
past this module, because past this module it is trusted twice.

Supabase signs access tokens two ways and this module supports both, never at
the same time:

*Asymmetric* (current). The project publishes a JWKS; tokens carry ``kid`` and
are verified with ES256 or RS256 against the matching public key.

*Symmetric* (legacy). The project has a shared secret and tokens are verified
with HS256.

Which one applies is decided by configuration, before the token is read. A
token's own ``alg`` header never selects the verification path — that is the
algorithm-confusion attack, where an attacker re-signs an RS256 token as HS256
using the public key as the HMAC secret and a naive verifier accepts it.

``aud``, ``iss`` and ``exp`` are all checked. ``iss`` in particular: without it
an access token minted by *any* Supabase project would verify against a JWKS
this service happened to have fetched, and every Supabase project in the world
is a valid issuer of correctly-shaped tokens.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Final
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKSet
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, ConfigurationError

logger = logging.getLogger(__name__)

#: The audience Supabase puts in every access token for a signed-in user.
AUTHENTICATED_AUDIENCE: Final[str] = "authenticated"

#: Asymmetric algorithms Supabase signs with. Listed explicitly and passed to
#: ``jwt.decode`` so the token header cannot nominate its own.
ASYMMETRIC_ALGORITHMS: Final[tuple[str, ...]] = ("ES256", "RS256")
SYMMETRIC_ALGORITHMS: Final[tuple[str, ...]] = ("HS256",)


class AuthenticatedUser(BaseModel):
    """The caller behind one verified access token.

    ``access_token`` is carried deliberately. Repositories present it to
    PostgREST so the database applies the same user's row level security, which
    means this object is a credential and not merely an identifier — it is
    never logged and never serialised into a response.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    email: str | None
    role: str
    access_token: str

    def __repr__(self) -> str:  # pragma: no cover - defensive, mirrors __str__
        return f"AuthenticatedUser(id={self.id!s}, role={self.role!r})"

    __str__ = __repr__


@dataclass
class _JwksCache:
    """A project's published keys, refetched on expiry or on an unknown kid.

    The minimum refresh interval is the important part. A token can name any
    ``kid`` it likes, and without a floor an attacker sending random ones would
    make this service hammer Supabase once per request.
    """

    url: str
    ttl_seconds: float
    min_refresh_seconds: float
    timeout_seconds: float
    transport: httpx.AsyncBaseTransport | None = None
    _keys: PyJWKSet | None = field(default=None, init=False)
    _fetched_at: float = field(default=0.0, init=False)

    async def key_for(self, kid: str | None) -> jwt.PyJWK:
        if kid is None:
            raise AuthenticationError("token has no key id")

        keys = self._keys
        now = time.monotonic()
        if keys is None or now - self._fetched_at >= self.ttl_seconds:
            keys = await self._fetch()

        try:
            return keys[kid]
        except KeyError:
            pass

        # An unknown kid is what a key rotation looks like from here, so one
        # refetch is warranted — but only if the last one was long enough ago.
        if time.monotonic() - self._fetched_at < self.min_refresh_seconds:
            raise AuthenticationError("token was signed with an unknown key")
        keys = await self._fetch()
        try:
            return keys[kid]
        except KeyError:
            raise AuthenticationError("token was signed with an unknown key") from None

    async def _fetch(self) -> PyJWKSet:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.get(self.url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # A stale key set beats no key set: if Supabase is briefly
            # unreachable, tokens signed with keys already held must keep
            # working rather than logging every user out.
            if self._keys is not None:
                logger.warning(
                    "jwks refresh failed; continuing with the cached key set",
                    extra={"error_type": type(exc).__name__},
                )
                return self._keys
            raise AuthenticationError("verification keys are unavailable") from exc

        try:
            keys = PyJWKSet.from_dict(payload)
        except (jwt.PyJWKSetError, KeyError, TypeError) as exc:
            if self._keys is not None:
                logger.warning("jwks response was unusable; keeping the cached key set")
                return self._keys
            raise AuthenticationError("verification keys are unusable") from exc

        self._keys = keys
        self._fetched_at = time.monotonic()
        return keys


class TokenVerifier:
    """Verifies Supabase access tokens for one project's configuration."""

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._jwks = _JwksCache(
            url=settings.jwks_url,
            ttl_seconds=settings.supabase_jwks_cache_seconds,
            min_refresh_seconds=settings.supabase_jwks_min_refresh_seconds,
            timeout_seconds=settings.supabase_timeout_seconds,
            transport=transport,
        )

    async def verify(self, token: str) -> AuthenticatedUser:
        """Return the caller behind ``token``.

        Raises :class:`~app.core.errors.AuthenticationError` for anything that
        does not verify, with a reason that names the failure without echoing
        the token.
        """
        if not self._settings.supabase_url:
            raise ConfigurationError("SUPABASE_URL is not set; access tokens cannot be verified")

        claims = await self._decode(token)

        subject = claims.get("sub")
        if not isinstance(subject, str):  # pragma: no cover
            # PyJWT rejects a non-string `sub` before this is reached, and the
            # `require` option rejects an absent one. Kept because the claims
            # are `Any` and the narrowing has to happen somewhere, and because
            # relying on a library's validation without a local guard is how a
            # dependency upgrade quietly changes what this service accepts.
            raise AuthenticationError("token carries no usable subject")
        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise AuthenticationError("token subject is not a user id") from exc

        role = claims.get("role")
        if role != AUTHENTICATED_AUDIENCE:
            # An anon-key JWT verifies against the same signing key and carries
            # role "anon". It is a valid token and it is not a user.
            raise AuthenticationError("token does not belong to a signed-in user")

        email = claims.get("email")
        return AuthenticatedUser(
            id=user_id,
            email=email if isinstance(email, str) and email else None,
            role=role,
            access_token=token,
        )

    async def _decode(self, token: str) -> dict[str, Any]:
        """Decode and verify, choosing the algorithm family from configuration.

        The configured mode decides which key and which algorithms are used.
        The token's own header never does.
        """
        secret = self._settings.supabase_jwt_secret
        key: Any
        if secret is not None and secret.get_secret_value():
            key = secret.get_secret_value()
            algorithms = SYMMETRIC_ALGORITHMS
        else:
            try:
                header = jwt.get_unverified_header(token)
            except jwt.PyJWTError as exc:
                raise AuthenticationError("token header is malformed") from exc
            key = (await self._jwks.key_for(header.get("kid"))).key
            algorithms = ASYMMETRIC_ALGORITHMS

        try:
            return dict(
                jwt.decode(
                    token,
                    key=key,
                    algorithms=list(algorithms),
                    audience=AUTHENTICATED_AUDIENCE,
                    issuer=self._settings.auth_issuer,
                    options={"require": ["exp", "sub", "aud", "iss"]},
                )
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("token has expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError("token was issued for a different audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError("token was issued by a different project") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise AuthenticationError(f"token is missing the {exc.claim} claim") from exc
        except jwt.PyJWTError as exc:
            # Covers a bad signature, a malformed token and an algorithm the
            # configured mode does not permit. The reason is deliberately not
            # narrowed further: distinguishing "bad signature" from "not a JWT"
            # tells an attacker which half of their guess was right.
            raise AuthenticationError("token could not be verified") from exc


def get_verifier(request: Request) -> TokenVerifier:
    """The application-wide verifier, built once at startup.

    Held on ``app.state`` rather than in a module global so that a test can
    build an application with an injected transport, and so two applications in
    one process never share a JWKS cache.
    """
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:  # pragma: no cover - create_app always installs one
        raise ConfigurationError("no token verifier is installed on this application")
    assert isinstance(verifier, TokenVerifier)
    return verifier


#: ``auto_error=False`` so a missing header reaches our own handler and produces
#: the same problem-details body as every other failure, rather than FastAPI's
#: bare ``{"detail": "Not authenticated"}``.
_bearer = HTTPBearer(auto_error=False, description="Supabase access token")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    """FastAPI dependency: the verified caller, or a 401.

    Depend on this from every route that touches user data. There is no
    "optional user" variant on purpose: a route that works both ways has two
    behaviours to secure, and the one nobody tests is the one that leaks.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("this endpoint requires a bearer access token")
    return await get_verifier(request).verify(credentials.credentials)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

#: For routes that must be authenticated but do not read the caller.
#:
#: Applied at the router with ``dependencies=[REQUIRE_USER]``. The alternative
#: — declaring an unused ``CurrentUser`` parameter — makes the authentication
#: look like an argument somebody forgot to use, and is exactly the sort of
#: thing a later cleanup removes.
REQUIRE_USER = Depends(get_current_user)


def build_verifier(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> TokenVerifier:
    """Construct the verifier the application factory installs."""
    return TokenVerifier(settings or get_settings(), transport=transport)
