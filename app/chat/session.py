"""대화 세션 — Redis 단순 키 ASSISTANT:CHAT:{memberId}, 30분 무활동이면 만료.

담는 것: 턴 이력 {질문 원문, 도구, 인자}, 슬롯(종목·투자자·기간), 종목 선택 대기 중인 도구 호출.
담지 않는 것: 도구 결과 값·답변 문장·개인 데이터 (C-01). 사용자가 직접 쓴 질문은 예외.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from redis.asyncio import Redis

KEY_PREFIX = "ASSISTANT:CHAT:"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class Turn:
    q: str
    tools: list[ToolCall]


@dataclass
class PendingItem:
    """아직 묻지 않은 종목 후보 — 다른 검색어로 후보가 여럿 나온 도구 호출"""

    call: ToolCall
    query: str
    candidates: list[dict[str, Any]]


@dataclass
class Pending:
    """종목 후보 되묻기 중. 사용자가 고르면 LLM 재호출 없이 calls 의 query 를 코드로 바꿔 재실행.

    calls 는 지금 묻는 query 로 후보를 낸 호출만 담는다. 다른 검색어로 후보가 나온 호출은 later 에 두고
    이번 선택 실행이 끝나면 차례로 묻는다 (2026-10-04, 다른 호출의 종목까지 바뀌던 문제 수정).
    """

    calls: list[ToolCall]
    query: str
    candidates: list[dict[str, Any]]
    later: list[PendingItem] = field(default_factory=list)


@dataclass
class ChatSession:
    turns: list[Turn] = field(default_factory=list)
    slots: dict[str, str] = field(default_factory=dict)  # stock / investor / period
    pending: Pending | None = None

    @classmethod
    def from_json(cls, raw: str) -> ChatSession:
        d = json.loads(raw)
        p = d.get("pending")
        return cls(
            turns=[Turn(t["q"], [ToolCall(**c) for c in t["tools"]]) for t in d.get("turns", [])],
            slots=d.get("slots", {}),
            pending=Pending(
                [ToolCall(**c) for c in p["calls"]], p["query"], p["candidates"],
                [PendingItem(ToolCall(**i["call"]), i["query"], i["candidates"]) for i in p.get("later", [])],
            ) if p else None,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class SessionStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def load(self, member_id: int) -> ChatSession:
        raw = await self._redis.get(f"{KEY_PREFIX}{member_id}")
        return ChatSession.from_json(raw) if raw else ChatSession()

    async def save(self, member_id: int, session: ChatSession) -> None:
        await self._redis.set(f"{KEY_PREFIX}{member_id}", session.to_json(), ex=self._ttl)


# ── 모델 입력 조립 ──


def _call_text(c: ToolCall) -> str:
    return f"{c.name} {json.dumps(c.args, ensure_ascii=False, separators=(',', ':'))}"


def render_history(session: ChatSession) -> str:
    lines = [f'- "{t.q}" → ' + "; ".join(_call_text(c) for c in t.tools) for t in session.turns]
    return "\n".join(lines)


def render_slots(session: ChatSession) -> str:
    labels = {"stock": "종목", "investor": "투자자", "period": "기간"}
    return " · ".join(f"{labels[k]}: {v}" for k, v in session.slots.items() if k in labels and v)


def estimate_tokens(text: str) -> int:
    """토큰 수 근사 — 한글은 글자당 1, 그 밖은 3글자당 1. compact 판단용이라 넉넉하게 잡는다"""
    wide = sum(1 for ch in text if ord(ch) > 0x7F)
    return wide + (len(text) - wide) // 3 + 1


def compact(session: ChatSession, budget: int) -> bool:
    """턴 이력이 토큰 예산을 넘으면 오래된 턴부터 버린다. 슬롯은 유지.

    6단계에서 이 함수만 LLM 요약으로 교체한다. 발동했으면 True.
    """
    compacted = False
    while session.turns and estimate_tokens(render_history(session)) > budget:
        session.turns.pop(0)
        compacted = True
    return compacted


def update_slots(session: ChatSession, calls: list[ToolCall], picked_name: str | None = None) -> None:
    """도구 인자에서 슬롯을 코드로 갱신 (모델 보조 입력)"""
    for c in calls:
        a = c.args
        if picked_name:
            session.slots["stock"] = picked_name
        elif (q := a.get("stockQuery")) is not None:
            session.slots["stock"] = ", ".join(q) if isinstance(q, list) else str(q)
        if inv := a.get("investor"):
            session.slots["investor"] = str(inv)
        if (days := a.get("days")) is not None:
            session.slots["period"] = f"{days}일"
        elif period := a.get("period"):
            session.slots["period"] = str(period)
        elif a.get("from") and a.get("to"):
            session.slots["period"] = f"{a['from']}~{a['to']}"
