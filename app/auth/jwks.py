"""비서 토큰(RS256) 검증 — 아키텍처 4.4.

kid → JWKS 공개키 → 서명·iss·exp → "assistant" ∈ aud → sub = memberId.
JWKS 는 1시간 캐시, 모르는 kid 가 오면 한 번만 다시 받는다. Redis·DB 조회 없음(stateless).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import jwt
from jwt import PyJWK

# Kotlin AssistantTokenService 의 SCOPE_CHAT_MARKET / SCOPE_CHAT 와 같은 값
SCOPE_MARKET = "chat.market"  # 로그인만으로 발급 — 공개 데이터(시세·수급·일정 등) 조회만 가능
SCOPE_PERSONAL = "chat"  # 2차 인증 후 발급 — 위에 더해 개인 데이터(계좌·보유·실현손익) 조회까지 가능


class TokenError(Exception):
    """검증 실패. 상위에서 401 로 바꾼다."""


@dataclass(frozen=True)
class Principal:
    member_id: int
    scope: str
    jti: str | None
    token: str  # Kotlin /internal 호출에 그대로 전파


JwksFetcher = Callable[[], dict]


def http_fetcher(url: str, timeout: float = 5.0) -> JwksFetcher:
    def fetch() -> dict:
        res = httpx.get(url, timeout=timeout)
        res.raise_for_status()
        return res.json()

    return fetch


class JwksVerifier:
    def __init__(self, fetcher: JwksFetcher, issuer: str, audience: str, cache_seconds: int = 3600) -> None:
        self._fetch = fetcher
        self._issuer = issuer
        self._audience = audience
        self._cache_seconds = cache_seconds
        self._keys: dict[str, PyJWK] = {}
        self._loaded_at = 0.0

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise TokenError(f"invalid token header: {e}") from e
        if header.get("alg") != "RS256":
            raise TokenError("unsupported alg")
        kid = header.get("kid")
        if not kid:
            raise TokenError("kid missing")
        key = self._key(kid)
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as e:
            raise TokenError(f"invalid token: {e}") from e
        try:
            member_id = int(claims["sub"])
        except (TypeError, ValueError) as e:
            raise TokenError("sub must be memberId") from e
        return Principal(
            member_id=member_id, scope=str(claims.get("scope", SCOPE_MARKET)), jti=claims.get("jti"), token=token
        )

    def _key(self, kid: str) -> PyJWK:
        if self._stale():
            self._reload()
        key = self._keys.get(kid)
        if key is None:
            self._reload()  # 키 회전 직후: 모르는 kid 는 1회 재로드
            key = self._keys.get(kid)
        if key is None:
            raise TokenError(f"unknown kid: {kid}")
        return key

    def _stale(self) -> bool:
        return time.monotonic() - self._loaded_at > self._cache_seconds

    def _reload(self) -> None:
        jwks = self._fetch()
        keys = {}
        for k in jwks.get("keys", []):
            if k.get("kty") == "RSA" and k.get("kid"):
                keys[k["kid"]] = PyJWK.from_dict(k)
        self._keys = keys
        self._loaded_at = time.monotonic()
