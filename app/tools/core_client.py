"""Kotlin /internal/assistant/tools/* 호출. 받은 비서 토큰을 그대로 전파한다 (아키텍처 4.5)."""

from __future__ import annotations

import httpx


class CoreClient:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def get_stock_quote(self, token: str, stk_cd: str) -> dict:
        res = await self._client.get(
            "/internal/assistant/tools/get_stock_quote",
            params={"stkCd": stk_cd},
            headers={"Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        return res.json()

    async def aclose(self) -> None:
        await self._client.aclose()
