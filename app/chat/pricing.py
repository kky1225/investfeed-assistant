"""모델 단가 ($/1M 토큰). 캐시 쓰기는 5분 캐시 = 입력 단가 ×1.25, 캐시 읽기는 별도 단가."""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


_PRICES: dict[str, Price] = {
    "claude-sonnet-5-5": Price(2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-5": Price(2.0, 10.0, 0.20, 2.50),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def cost_usd(self, model: str) -> float:
        p = _PRICES.get(model)
        if p is None:
            log.error("단가 미등록 모델 %s — Sonnet 단가로 계산", model)
            p = _PRICES["claude-sonnet-5-5"]
        return (
            self.input_tokens * p.input
            + self.output_tokens * p.output
            + self.cache_read_tokens * p.cache_read
            + self.cache_write_tokens * p.cache_write
        ) / 1_000_000
