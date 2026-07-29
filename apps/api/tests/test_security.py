"""Tests for Supabase access token verification.

Structured around what an attacker would try, because a verifier is only as
good as the cases it refuses. Every negative here is a token that is
well-formed and would be accepted by a verifier missing one check.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from app.core.errors import AuthenticationError, ConfigurationError
from app.core.security import TokenVerifier
from tests.auth_fixtures import ISSUER, JwksServer, SigningKey, claims, settings

#: A secret long enough that PyJWT does not warn about its length. The tests
#: care about which secret verifies, not how strong it is.
SHARED_SECRET = "a-shared-secret-of-at-least-32-bytes-long"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _hs256_token(payload: dict[str, Any], *, secret: bytes, kid: str) -> str:
    """An HS256 JWT built without a JWT library.

    Needed for the algorithm-confusion case: PyJWT refuses to sign with an
    asymmetric key as the HMAC secret, and an attacker is under no such
    constraint.
    """
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}).encode())
    body = _b64(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


# --------------------------------------------------------------- happy path


async def test_a_valid_token_yields_its_user() -> None:
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(settings(), transport=server.transport())
    subject = uuid4()

    user = await verifier.verify(key.sign(claims(subject=subject, email="ada@example.test")))

    assert user.id == subject
    assert user.email == "ada@example.test"
    assert user.role == "authenticated"


async def test_a_token_without_an_email_claim_is_still_a_user() -> None:
    """Not every provider returns one, and the account still exists."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())

    user = await verifier.verify(key.sign(claims(email=None)))

    assert user.email is None


async def test_the_access_token_is_carried_for_the_database() -> None:
    """Repositories present it to PostgREST so RLS applies to the same user."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    token = key.sign(claims())

    user = await verifier.verify(token)

    assert user.access_token == token


async def test_the_user_never_renders_its_own_token() -> None:
    """It is a credential. A log line that interpolates the caller must not leak it."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    token = key.sign(claims())

    user = await verifier.verify(token)

    assert token not in repr(user)
    assert token not in str(user)


# ------------------------------------------------------------ forged tokens


async def test_a_tampered_payload_is_rejected() -> None:
    """The classic attack: edit `sub`, keep the signature, hope nobody checks."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    header, _original, signature = key.sign(claims()).split(".")
    other = key.sign(claims(subject=uuid4())).split(".")[1]

    with pytest.raises(AuthenticationError, match="could not be verified"):
        await verifier.verify(f"{header}.{other}.{signature}")


async def test_a_token_signed_by_another_key_is_rejected() -> None:
    """A key the project never published, announced under a kid that it did."""
    published = SigningKey.generate("key-1")
    attacker = SigningKey(kid="key-1", private_key=SigningKey.generate("x").private_key)
    verifier = TokenVerifier(settings(), transport=JwksServer([published]).transport())

    with pytest.raises(AuthenticationError, match="could not be verified"):
        await verifier.verify(attacker.sign(claims()))


async def test_an_expired_token_is_rejected() -> None:
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())

    with pytest.raises(AuthenticationError, match="expired"):
        await verifier.verify(key.sign(claims(expires_in=-60)))


async def test_a_token_from_another_supabase_project_is_rejected() -> None:
    """Every Supabase project mints correctly-shaped tokens. Only ours count."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())

    with pytest.raises(AuthenticationError, match="different project"):
        await verifier.verify(key.sign(claims(issuer="https://someone-else.supabase.co/auth/v1")))


async def test_a_token_for_another_audience_is_rejected() -> None:
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())

    with pytest.raises(AuthenticationError, match="different audience"):
        await verifier.verify(key.sign(claims(audience="supabase-admin")))


async def test_an_anon_key_token_is_not_a_user() -> None:
    """It verifies against the same key and carries role `anon`. It is not a login."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())

    with pytest.raises(AuthenticationError, match="signed-in user"):
        await verifier.verify(key.sign(claims(audience="authenticated", role="anon")))


async def test_a_token_missing_a_required_claim_is_rejected() -> None:
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    payload = claims()
    del payload["exp"]

    with pytest.raises(AuthenticationError, match="missing the exp claim"):
        await verifier.verify(key.sign(payload))


async def test_a_subject_that_is_not_a_user_id_is_rejected() -> None:
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    payload = claims()
    payload["sub"] = "not-a-uuid"

    with pytest.raises(AuthenticationError, match="not a user id"):
        await verifier.verify(key.sign(payload))


async def test_a_non_string_subject_is_rejected() -> None:
    """PyJWT refuses it during decoding, so it never reaches the local guard."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    payload = claims()
    payload["sub"] = 12345

    with pytest.raises(AuthenticationError, match="could not be verified"):
        await verifier.verify(key.sign(payload))


async def test_a_token_that_is_not_a_jwt_at_all_is_rejected() -> None:
    verifier = TokenVerifier(settings(), transport=JwksServer([]).transport())

    with pytest.raises(AuthenticationError, match="header is malformed"):
        await verifier.verify("this-is-not-a-token")


async def test_a_token_with_no_key_id_is_rejected() -> None:
    """Without a kid there is no key to select, and guessing is not verification."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    unkidded = jwt.encode(claims(), key.private_key, algorithm="ES256")

    with pytest.raises(AuthenticationError, match="no key id"):
        await verifier.verify(unkidded)


# --------------------------------------------------- algorithm confusion


async def test_an_hs256_token_is_refused_under_asymmetric_configuration() -> None:
    """The algorithm-confusion attack.

    An attacker re-signs the token as HS256 using the project's *public* key as
    the HMAC secret. A verifier that reads `alg` from the token header and
    fetches the matching JWK would accept it. This one takes its algorithm list
    from configuration, so the token's own header is not consulted.
    """
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(settings(), transport=JwksServer([key]).transport())
    public_pem = key.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Assembled by hand rather than through `jwt.encode`, which refuses to use
    # an asymmetric key as an HMAC secret. That refusal protects careless
    # *signers*; an attacker has no such library in the way, so the forgery has
    # to be built the way they would build it for the test to mean anything.
    forged = _hs256_token(claims(), secret=public_pem, kid="key-1")

    with pytest.raises(AuthenticationError, match="could not be verified"):
        await verifier.verify(forged)


async def test_an_asymmetric_token_is_refused_under_symmetric_configuration() -> None:
    """The mirror case: a legacy project must not accept ES256 tokens either."""
    key = SigningKey.generate("key-1")
    verifier = TokenVerifier(
        settings(supabase_jwt_secret=SHARED_SECRET),
        transport=JwksServer([key]).transport(),
    )

    with pytest.raises(AuthenticationError, match="could not be verified"):
        await verifier.verify(key.sign(claims()))


# ------------------------------------------------------------- legacy HS256


async def test_a_symmetric_project_verifies_hs256_tokens() -> None:
    server = JwksServer([])
    verifier = TokenVerifier(
        settings(supabase_jwt_secret=SHARED_SECRET), transport=server.transport()
    )
    subject = uuid4()
    token = jwt.encode(claims(subject=subject), SHARED_SECRET, algorithm="HS256")

    user = await verifier.verify(token)

    assert user.id == subject
    assert server.fetches == 0, "a symmetric project must never fetch a key set"


async def test_a_symmetric_project_rejects_the_wrong_secret() -> None:
    verifier = TokenVerifier(
        settings(supabase_jwt_secret=SHARED_SECRET), transport=JwksServer([]).transport()
    )
    token = jwt.encode(claims(), "a-different-secret-of-at-least-32-bytes", algorithm="HS256")

    with pytest.raises(AuthenticationError, match="could not be verified"):
        await verifier.verify(token)


async def test_an_empty_jwt_secret_falls_through_to_the_key_set() -> None:
    """A blank variable in a `.env` must not silently disable verification."""
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(settings(supabase_jwt_secret=""), transport=server.transport())

    await verifier.verify(key.sign(claims()))

    assert server.fetches == 1


# ----------------------------------------------------------- the key cache


async def test_the_key_set_is_fetched_once_for_many_tokens() -> None:
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(settings(), transport=server.transport())

    for _ in range(5):
        await verifier.verify(key.sign(claims()))

    assert server.fetches == 1


async def test_the_key_set_is_refetched_once_it_expires() -> None:
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(
        settings(supabase_jwks_cache_seconds=0.01), transport=server.transport()
    )

    await verifier.verify(key.sign(claims()))
    await asyncio.sleep(0.02)
    await verifier.verify(key.sign(claims()))

    assert server.fetches == 2


async def test_an_unknown_key_id_triggers_at_most_one_refetch() -> None:
    """A rotation looks like an unknown kid, so one refetch is right.

    Without the minimum refresh interval, a token carrying a random kid would
    cost one outbound fetch per request — a denial of service against Supabase
    that any unauthenticated caller could mount.
    """
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(settings(), transport=server.transport())
    stranger = SigningKey.generate("key-99")

    for _ in range(10):
        with pytest.raises(AuthenticationError, match="unknown key"):
            await verifier.verify(stranger.sign(claims()))

    assert server.fetches == 1


async def test_a_rotated_key_is_picked_up_after_the_refresh_floor() -> None:
    old = SigningKey.generate("key-1")
    server = JwksServer([old])
    verifier = TokenVerifier(
        settings(supabase_jwks_min_refresh_seconds=0.01), transport=server.transport()
    )
    await verifier.verify(old.sign(claims()))

    new = SigningKey.generate("key-2")
    server.keys.append(new)
    await asyncio.sleep(0.02)

    user = await verifier.verify(new.sign(claims()))

    assert user.role == "authenticated"
    assert server.fetches == 2


async def test_a_brief_outage_does_not_invalidate_cached_keys() -> None:
    """Supabase being unreachable must not sign every user out."""
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(
        settings(supabase_jwks_cache_seconds=0.01), transport=server.transport()
    )
    await verifier.verify(key.sign(claims()))

    server.fail_next(1)
    await asyncio.sleep(0.02)
    user = await verifier.verify(key.sign(claims()))

    assert user.role == "authenticated"


async def test_an_unusable_key_set_does_not_invalidate_cached_keys() -> None:
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    verifier = TokenVerifier(
        settings(supabase_jwks_cache_seconds=0.01), transport=server.transport()
    )
    await verifier.verify(key.sign(claims()))

    server.body = {"not": "a key set"}
    await asyncio.sleep(0.02)
    user = await verifier.verify(key.sign(claims()))

    assert user.role == "authenticated"


async def test_an_unreachable_key_set_with_no_cache_is_an_auth_failure() -> None:
    """No keys and no cache means nothing can be verified, so nothing is trusted."""
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    server.fail_next(1)
    verifier = TokenVerifier(settings(), transport=server.transport())

    with pytest.raises(AuthenticationError, match="keys are unavailable"):
        await verifier.verify(key.sign(claims()))


async def test_an_unusable_key_set_with_no_cache_is_an_auth_failure() -> None:
    key = SigningKey.generate("key-1")
    server = JwksServer([key])
    server.body = {"not": "a key set"}
    verifier = TokenVerifier(settings(), transport=server.transport())

    with pytest.raises(AuthenticationError, match="keys are unusable"):
        await verifier.verify(key.sign(claims()))


async def test_a_key_set_that_is_not_json_with_no_cache_is_an_auth_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    verifier = TokenVerifier(settings(), transport=httpx.MockTransport(handler))
    key = SigningKey.generate("key-1")

    with pytest.raises(AuthenticationError, match="keys are unavailable"):
        await verifier.verify(key.sign(claims()))


# ------------------------------------------------------------ configuration


async def test_an_unconfigured_project_cannot_verify_anything() -> None:
    """Failing loudly beats a service that accepts nothing and says 401."""
    verifier = TokenVerifier(settings(supabase_url=""), transport=JwksServer([]).transport())

    with pytest.raises(ConfigurationError, match="SUPABASE_URL"):
        await verifier.verify("any-token")


def test_the_issuer_and_jwks_url_are_derived_from_the_project_url() -> None:
    assert settings().auth_issuer == ISSUER
    assert settings().jwks_url.endswith("/.well-known/jwks.json")


def test_a_trailing_slash_on_the_project_url_does_not_double_up() -> None:
    """A copied-and-pasted dashboard URL keeps its slash. It must still work."""
    configured = settings(supabase_url="https://project.supabase.test/")

    assert configured.auth_issuer == ISSUER
    assert configured.postgrest_url == "https://project.supabase.test/rest/v1"
