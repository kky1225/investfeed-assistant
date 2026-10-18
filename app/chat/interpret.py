"""질문 해석 — LLM 1회 function calling. 결과는 도구 호출 목록 또는 reject/ask_user 라벨뿐이다.

Sonnet 5.5 는 tool_choice any 를 받지 않아 auto + strict + 프롬프트 지시로 도구 호출을 유도한다.
도구 없이 텍스트만 오거나(NO_TOOL) 안전 거절(REFUSAL) 이면 텍스트는 버리고 고정 응답으로 처리한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import anthropic

from app.chat.pricing import Usage
from app.chat.prompts import ASK_TOOL, REJECT_TOOL, SYSTEM_PROMPT, interpret_tools
from app.chat.session import ChatSession, ToolCall, render_history, render_slots

log = logging.getLogger(__name__)

_WEEKDAYS = "월화수목금토일"


@dataclass
class Interpretation:
    kind: str  # TOOLS / REJECT / ASK_USER / NO_TOOL / REFUSAL / ERROR
    calls: list[ToolCall] = field(default_factory=list)
    reason: str | None = None  # REJECT 사유 / ASK_USER missing
    usage: Usage = field(default_factory=Usage)


def dedupe_calls(calls: list[ToolCall]) -> list[ToolCall]:
    """같은 도구를 겹쳐 고른 호출을 하나로 합친다 — 같은 카드가 두 번 나오지 않게.

    완전히 같은 호출은 하나만 남기고, 같은 도구에서 한 호출의 인자가 다른 호출의 인자에 모두 포함되면
    (예: 국채 {date} 와 {market: KR, date}) 더 구체적인 쪽만 남긴다. 인자가 서로 다르면(다른 종목 등) 둘 다 둔다.
    """
    kept: list[ToolCall] = []
    for c in calls:
        if any(k.name == c.name and c.args.items() <= k.args.items() for k in kept):
            continue  # 이미 남긴 호출과 같거나 그보다 덜 구체적
        kept = [k for k in kept if not (k.name == c.name and k.args.items() <= c.args.items())]
        kept.append(c)
    if len(kept) < len(calls):
        log.info("겹치는 도구 호출 합침: %d → %d (%s)", len(calls), len(kept), ", ".join(k.name for k in kept))
    return kept


def build_user_text(question: str, session: ChatSession, today: date) -> str:
    parts = []
    if history := render_history(session):
        parts.append(f"[이전 대화]\n{history}")
    if slots := render_slots(session):
        parts.append(f"[현재 맥락] {slots}")
    parts.append(f"[오늘] {today.isoformat()}({_WEEKDAYS[today.weekday()]})")
    parts.append(f"[질문] {question}")
    return "\n\n".join(parts)


def _usage(resp: anthropic.types.Message) -> Usage:
    u = resp.usage
    return Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0,
        cache_write_tokens=u.cache_creation_input_tokens or 0,
    )


async def interpret(
    llm: anthropic.AsyncAnthropic,
    model: str,
    effort: str,
    max_tokens: int,
    question: str,
    session: ChatSession,
    today: date,
) -> Interpretation:
    try:
        resp = await llm.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=interpret_tools(),
            tool_choice={"type": "auto"},
            output_config={"effort": effort},
            messages=[{"role": "user", "content": build_user_text(question, session, today)}],
        )
    except anthropic.APIStatusError as e:
        log.error("질문 해석 LLM 오류 status=%s type=%s", e.status_code, type(e).__name__)
        return Interpretation("ERROR", reason="LLM")
    except anthropic.APIConnectionError as e:
        log.error("질문 해석 LLM 연결 실패: %s", type(e).__name__)
        return Interpretation("ERROR", reason="LLM")

    usage = _usage(resp)
    if resp.stop_reason == "refusal":
        return Interpretation("REFUSAL", reason="REFUSAL", usage=usage)

    calls = [ToolCall(b.name, dict(b.input)) for b in resp.content if b.type == "tool_use"]
    if not calls:
        return Interpretation("NO_TOOL", reason="NO_TOOL", usage=usage)
    # 우선순위: reject > ask_user > 실제 도구 (거절 라벨이 섞이면 조회하지 않는다)
    if rej := next((c for c in calls if c.name == REJECT_TOOL), None):
        return Interpretation("REJECT", [rej], reason=str(rej.args.get("reason")), usage=usage)
    if ask := next((c for c in calls if c.name == ASK_TOOL), None):
        return Interpretation("ASK_USER", [ask], reason=str(ask.args.get("missing")), usage=usage)
    return Interpretation("TOOLS", dedupe_calls(calls), usage=usage)
