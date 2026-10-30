import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.auth.jwks import SCOPE_MARKET, SCOPE_PERSONAL, JwksVerifier, TokenError

ISSUER = "investfeed-core"
AUDIENCE = "assistant"
KID = "k1"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def fetch_calls():
    return []


@pytest.fixture
def verifier(private_key, fetch_calls):
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = KID

    def fetch() -> dict:
        fetch_calls.append(1)
        return {"keys": [jwk]}

    return JwksVerifier(fetch, ISSUER, AUDIENCE)


def _token(key, *, kid: str = KID, alg: str = "RS256", **overrides) -> str:
    claims = {"sub": "42", "iss": ISSUER, "aud": [AUDIENCE], "exp": int(time.time()) + 60} | overrides
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


def test_valid_token_returns_principal(verifier, private_key):
    token = _token(private_key, scope=SCOPE_PERSONAL, jti="j1")

    principal = verifier.verify(token)

    assert principal.member_id == 42
    assert principal.scope == SCOPE_PERSONAL
    assert principal.jti == "j1"
    assert principal.token == token


def test_scope_defaults_to_market(verifier, private_key):
    assert verifier.verify(_token(private_key)).scope == SCOPE_MARKET


def test_rejects_hs256_user_jwt(verifier):
    token = _token("user-jwt-secret-that-is-at-least-32-bytes", alg="HS256")

    with pytest.raises(TokenError, match="unsupported alg"):
        verifier.verify(token)


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": ["other"]},
        {"iss": "someone-else"},
        {"exp": int(time.time()) - 60},
        {"sub": "not-a-member-id"},
    ],
)
def test_rejects_invalid_claims(verifier, private_key, overrides):
    with pytest.raises(TokenError):
        verifier.verify(_token(private_key, **overrides))


def test_unknown_kid_reloads_jwks_once(verifier, private_key, fetch_calls):
    with pytest.raises(TokenError, match="unknown kid"):
        verifier.verify(_token(private_key, kid="rotated"))

    assert len(fetch_calls) == 2
