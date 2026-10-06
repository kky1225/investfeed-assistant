"""Kotlin /internal/assistant/tools/* 호출. 받은 비서 토큰을 그대로 전파한다 (아키텍처 4.5).

응답은 Kotlin ToolResponse 봉투 {ok, data, error, candidates, asOf, source}.
인자 오류·종목 미확정은 HTTP 200 + ok=false.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.tools.registry import REGISTRY, ToolSpec


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    candidates: list[dict[str, Any]] | None = None
    query: str | None = None  # 후보를 낸 종목 검색어
    as_of: str | None = None
    source: str | None = None

    @classmethod
    def from_envelope(cls, body: dict[str, Any]) -> ToolResult:
        return cls(
            ok=bool(body.get("ok")),
            data=body.get("data"),
            error=body.get("error"),
            candidates=body.get("candidates"),
            query=body.get("query"),
            as_of=body.get("asOf"),
            source=body.get("source"),
        )


class CoreClient:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def call(self, token: str, tool: str, args: dict[str, Any] | None = None) -> ToolResult:
        """도구 이름과 인자로 Kotlin 을 부른다. 배열 인자(stockQuery 등)는 같은 키를 반복하는 쿼리스트링으로."""
        spec: ToolSpec | None = REGISTRY.get(tool)
        if spec is None:
            return ToolResult(ok=False, error=f"알 수 없는 도구: {tool}")
        params: list[tuple[str, str]] = []
        for k, v in (args or {}).items():
            if v is None:
                continue
            if isinstance(v, list):
                params.extend((k, str(x)) for x in v)
            elif isinstance(v, bool):
                params.append((k, "true" if v else "false"))
            else:
                params.append((k, str(v)))
        res = await self._client.get(spec.path, params=params, headers={"Authorization": f"Bearer {token}"})
        if res.status_code == 401:
            return ToolResult(ok=False, error="비서 토큰이 유효하지 않습니다")
        res.raise_for_status()
        return ToolResult.from_envelope(res.json())

    async def save_turn(self, token: str, body: dict[str, Any]) -> ToolResult:
        """턴 종료 시 Kotlin 타임라인·사용량 로그에 저장 (POST /internal/assistant/timeline/turns)"""
        res = await self._client.post(
            "/internal/assistant/timeline/turns", json=body, headers={"Authorization": f"Bearer {token}"}
        )
        if res.status_code == 401:
            return ToolResult(ok=False, error="비서 토큰이 유효하지 않습니다")
        res.raise_for_status()
        return ToolResult.from_envelope(res.json())

    async def aclose(self) -> None:
        await self._client.aclose()
