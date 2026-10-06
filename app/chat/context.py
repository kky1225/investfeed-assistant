"""한 턴의 실행 문맥. 카드 본문(공개 데이터·카드 참조)은 그래프 state 가 아니라 여기 둔다 — 턴이 끝나면 버린다."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.chat.guard import Guard
from app.chat.pricing import Usage
from app.chat.session import ChatSession, PendingItem, SessionStore
from app.config import Settings
from app.tools.core_client import CoreClient


@dataclass
class Deps:
    settings: Settings
    core: CoreClient
    llm: anthropic.AsyncAnthropic
    store: SessionStore
    guard: Guard


@dataclass
class TurnContext:
    deps: Deps
    member_id: int
    token: str
    request_id: str
    question: str
    session: ChatSession
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None]

    route: str = "ERROR"  # TOOL / REJECT / ASK_USER / PICK / BLOCKED / ERROR
    reason: str | None = None
    reply: str = ""
    cards: list[dict[str, Any]] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    tool_errors: int = 0
    llm_calls: int = 0
    usage: Usage = field(default_factory=Usage)
    compacted: bool = False
    picked_name: str | None = None
    carried: list[PendingItem] = field(default_factory=list)  # 종목 선택 후에도 남은, 아직 묻지 않은 후보

    def emit(self, event: str, data: dict[str, Any]) -> None:
        self.queue.put_nowait((event, data))

    def add_card(self, card: dict[str, Any]) -> None:
        self.cards.append(card)
        self.emit("card", card)
