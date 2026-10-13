"""Q&A 한 턴 실행. SSE 연결과 분리된 백그라운드 작업으로 돌아서, 사용자가 창을 닫아도 턴 저장까지 끝낸다.

SSE 이벤트: meta {requestId} → card {kind, ref|payload, asOf, source, error}*
         → reply {text, route} → done {requestId, saved}
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.chat import replies
from app.chat.context import Deps, TurnContext
from app.chat.execute import STOCK_CHOICE
from app.chat.prompts import ASK_TOOL, REJECT_TOOL
from app.chat.session import ToolCall, Turn, update_slots

log = logging.getLogger(__name__)

_CARD_FIELDS = ("kind", "ref", "payload", "args", "asOf", "source", "error")


def _final_reply(ctx: TurnContext) -> str:
    if ctx.reply:
        return ctx.reply
    kinds = {c["kind"] for c in ctx.cards}
    if STOCK_CHOICE in kinds:
        return replies.CHOOSE_STOCK
    if "CONFIRM_PRICE_ALERT" in kinds:
        return replies.CONFIRM_ALERT
    if ctx.cards and all(c.get("error") for c in ctx.cards):
        return replies.ALL_FAILED
    return replies.DONE


def _record_history(ctx: TurnContext, calls: list[dict[str, Any]]) -> None:
    """세션 턴 이력 갱신 — {질문 원문, 도구, 인자} 만. 선택(PICK)은 guard 가 이전 턴을 고쳐 두었다"""
    if ctx.route == "PICK":
        if ctx.picked_name:
            ctx.session.slots["stock"] = ctx.picked_name
        return
    if ctx.route == "AUTH_REQUIRED":  # 아직 실행 전 — 인증 후 이어서 실행(RESUME)될 때 남긴다
        return
    if ctx.route == "REJECT":
        ctx.session.turns.append(Turn(ctx.question, [ToolCall(REJECT_TOOL, {"reason": ctx.reason})]))
    elif ctx.route == "ASK_USER":
        ctx.session.turns.append(Turn(ctx.question, [ToolCall(ASK_TOOL, {"missing": ctx.reason})]))
    elif calls:  # TOOL·RESUME 또는 실행 중 타임아웃
        tool_calls = [ToolCall(c["name"], c["args"]) for c in calls]
        ctx.session.turns.append(Turn(ctx.question, tool_calls))
        update_slots(ctx.session, tool_calls)


async def run_turn(graph, deps: Deps, ctx: TurnContext, pick: dict[str, Any] | None, resume: bool = False) -> None:
    started = time.monotonic()
    state: dict[str, Any] = {}
    try:
        async with asyncio.timeout(deps.settings.chat_timeout_seconds):
            # ainvoke 대신 astream: 단계마다 상태를 받아 두어, 실행 중 타임아웃이 나도 interpret 까지의 상태(calls)가 남는다
            # → _record_history 가 "이 질문에 이 도구를 쓰려 했다"를 이력에 남겨 다음 질문이 이어받는다
            async for chunk in graph.astream(
                {"member_id": ctx.member_id, "question": ctx.question, "pick": pick, "resume": resume},
                config={"configurable": {"ctx": ctx}},
                stream_mode="values",
            ):
                state = chunk
    except TimeoutError:
        log.error("비서 턴 타임아웃 request=%s route=%s", ctx.request_id, ctx.route)
        ctx.route, ctx.reason, ctx.reply = "ERROR", "TIMEOUT", replies.TIMEOUT
    except Exception:
        log.exception("비서 턴 실패 request=%s", ctx.request_id)
        ctx.route, ctx.reason, ctx.reply = "ERROR", "LLM", replies.LLM_ERROR

    # 여기부터는 성공·실패와 무관하게 항상 실행 — 답변 문구, 세션 이력, Kotlin 턴·사용량 저장
    reply = _final_reply(ctx)
    ctx.emit("reply", {"text": reply, "route": ctx.route})

    try:
        _record_history(ctx, state.get("calls") or [])
        await deps.store.save(ctx.member_id, ctx.session)
    except Exception:
        log.exception("비서 세션 저장 실패 request=%s", ctx.request_id)

    saved = await _save_turn(deps, ctx, reply, int((time.monotonic() - started) * 1000))
    ctx.emit("done", {"requestId": ctx.request_id, "saved": saved})
    ctx.queue.put_nowait(None)


async def _save_turn(deps: Deps, ctx: TurnContext, reply: str, latency_ms: int) -> bool:
    model = deps.settings.assistant_model if ctx.llm_calls else None
    body = {
        "requestId": ctx.request_id,
        "question": ctx.question,
        "replyText": reply,
        "cards": [{k: c[k] for k in _CARD_FIELDS if c.get(k) is not None} for c in ctx.cards],
        "log": {
            "route": ctx.route,
            "reason": ctx.reason,
            "tools": ctx.tool_names,
            "toolErrorCount": ctx.tool_errors,
            "llmCalls": ctx.llm_calls,
            "model": model,
            "inputTokens": ctx.usage.input_tokens,
            "outputTokens": ctx.usage.output_tokens,
            "cacheReadTokens": ctx.usage.cache_read_tokens,
            "cacheWriteTokens": ctx.usage.cache_write_tokens,
            "costUsd": round(ctx.usage.cost_usd(model), 6) if model else 0,
            "compacted": ctx.compacted,
            "latencyMs": latency_ms,
        },
    }
    try:
        res = await deps.core.save_turn(ctx.token, body)
    except Exception:
        log.exception("비서 턴 저장 호출 실패 request=%s", ctx.request_id)
        return False
    if not res.ok:
        log.error("비서 턴 저장 실패 request=%s: %s", ctx.request_id, res.error)
    return res.ok
