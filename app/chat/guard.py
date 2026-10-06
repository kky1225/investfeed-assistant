"""호출 상한 — 회원별 분당 LLM 호출 수, 서비스 전체 월 비용. 판정은 Redis 카운터, 기록은 Kotlin assistant_chat_log.

Redis 가 비워지면 카운터도 0 부터 다시 센다 (월 비용은 콘솔 스펜드 리밋이 최종 방어선).
"""

from __future__ import annotations

import time
from datetime import datetime

from redis.asyncio import Redis

RATE_PREFIX = "ASSISTANT:RATE:"
COST_PREFIX = "ASSISTANT:COST:"
_MICRO = 1_000_000


def _cost_key(now: datetime) -> str:
    return f"{COST_PREFIX}{now:%Y%m}"


class Guard:
    def __init__(self, redis: Redis, rate_per_minute: int, monthly_cap_usd: float) -> None:
        self._redis = redis
        self._rate = rate_per_minute
        self._cap_micro = int(monthly_cap_usd * _MICRO)

    async def check(self, member_id: int) -> str | None:
        """막히면 사유(COST_MONTH / RATE_MINUTE), 통과면 None. 통과 시 분당 카운터를 1 올린다"""
        spent = await self._redis.get(_cost_key(datetime.now()))
        if spent is not None and int(spent) >= self._cap_micro:
            return "COST_MONTH"
        key = f"{RATE_PREFIX}{member_id}:{int(time.time()) // 60}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 120)
        return "RATE_MINUTE" if count > self._rate else None

    async def add_cost(self, usd: float) -> None:
        if usd <= 0:
            return
        key = _cost_key(datetime.now())
        await self._redis.incrby(key, round(usd * _MICRO))
        await self._redis.expire(key, 40 * 24 * 3600)
