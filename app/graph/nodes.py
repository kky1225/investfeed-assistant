"""3노드 직선: guard → interpret → execute (5단계, 2026-09-30).

- guard: 종목 선택·2차 인증 후 이어서 실행이면 대기 중 도구 호출을 바로 execute 로, 아니면 호출 상한 확인
- interpret: LLM 1회 — 도구 호출 목록 또는 reject/ask_user 라벨
- execute: Kotlin 도구 병렬 실행, 카드 전송
사용자에게 보이는 문장은 app.chat.replies 의 고정 문구뿐이다.
"""

from __future__ import annotations

from datetime import date

from langgraph.config import get_config

from app.chat import replies
from app.chat.context import TurnContext
from app.chat.execute import apply_stock_choice, run_tools_and_send_cards
from app.chat.interpret import interpret as llm_interpret
from app.chat.session import AuthPending, ToolCall, compact
from app.graph.state import ChatState
from app.tools.registry import requires_personal


def _ctx() -> TurnContext:
    return get_config()["configurable"]["ctx"]


def _calls(state: ChatState) -> list[ToolCall]:
    return [ToolCall(c["name"], c["args"]) for c in state.get("calls", [])]


def _needs_auth(ctx: TurnContext, calls: list[ToolCall]) -> bool:
    return not ctx.personal and any(requires_personal(c.name) for c in calls)


def _ask_auth(ctx: TurnContext, calls: list[ToolCall]) -> ChatState:
    """개인 도구를 실행하지 않고 2차 인증을 요청한다. 화면이 인증 후 같은 요청을 이어서 보낸다"""
    ctx.route, ctx.reply = "AUTH_REQUIRED", replies.AUTH_REQUIRED
    ctx.tool_names = [c.name for c in calls]  # 사용량 로그용 — 무엇을 하려다 멈췄는지
    return {"route": "AUTH_REQUIRED"}


async def guard(state: ChatState) -> ChatState:
    ctx = _ctx()
    # 2차 인증 후 이어서 실행: 인증 전에 LLM 이 골라 둔 도구 호출을 그대로 execute 로 (LLM 재호출 없음)
    if state.get("resume"):
        waiting = ctx.session.auth_pending
        if waiting is None:
            ctx.route, ctx.reply = "RESUME", replies.RESUME_EXPIRED
            return {"route": "RESUME_EXPIRED"}
        if _needs_auth(ctx, waiting.calls):
            return _ask_auth(ctx, waiting.calls)
        ctx.session.auth_pending = None
        ctx.question = waiting.question
        ctx.route = "RESUME"
        return {"route": "RESUME", "calls": [{"name": c.name, "args": c.args} for c in waiting.calls]}

    # 후보 카드 클릭이면 요청에 pick 이 있다 → 보류해 둔 도구 호출에 고른 종목을 넣어 LLM 없이 바로 execute.
    # 직접 입력한 질문은 pick 이 없어 아래 상한 확인 후 interpret(LLM) 로 간다 (내용으로 판단하지 않는다)
    if pick := state.get("pick"):
        pending = ctx.session.pending
        if pending is None:
            ctx.route, ctx.reply = "PICK", replies.PICK_EXPIRED
            return {"route": "PICK_EXPIRED"}
        if _needs_auth(ctx, pending.calls):  # 대기는 그대로 둔다 — 인증 후 같은 선택을 다시 보낸다
            return _ask_auth(ctx, pending.calls)
        # 실행용은 종목 코드로(정확한 조회), 이력용은 종목 이름으로(다음 질문의 LLM 이 읽고 이어받게) 두 번 바꾼다
        calls = apply_stock_choice(pending.calls, pending.query, str(pick["code"]), pick.get("market"))
        # 이력에는 선택한 종목명으로 남겨 다음 질문이 이어받게 한다
        named = apply_stock_choice(pending.calls, pending.query, str(pick.get("name") or pick["code"]), None)
        for turn in reversed(ctx.session.turns):
            if any(c in pending.calls for c in turn.tools):
                turn.tools = [named[pending.calls.index(c)] if c in pending.calls else c for c in turn.tools]
                break
        ctx.carried = pending.later  # 다른 검색어 후보는 이번 실행 뒤 이어서 묻는다
        ctx.session.pending = None
        ctx.picked_name = pick.get("name")
        ctx.route = "PICK"
        return {"route": "PICK", "calls": [{"name": c.name, "args": c.args} for c in calls]}

    if blocked := await ctx.deps.guard.check(ctx.member_id):
        ctx.route, ctx.reason = "BLOCKED", blocked
        ctx.reply = replies.COST_LIMIT if blocked == "COST_MONTH" else replies.RATE_LIMIT
        return {"route": "BLOCKED"}
    return {"route": "INTERPRET"}


async def interpret(state: ChatState) -> ChatState:
    ctx = _ctx()
    s = ctx.deps.settings
    ctx.session.pending = None  # 새 질문이면 종목 선택 대기는 버린다
    ctx.session.auth_pending = None  # 2차 인증 대기도 마찬가지
    ctx.compacted = compact(ctx.session, s.history_token_budget)
    res = await llm_interpret(
        ctx.deps.llm, s.assistant_model, s.assistant_effort, s.assistant_max_tokens,
        state["question"], ctx.session, date.today(),
    )
    if res.kind != "ERROR":
        ctx.llm_calls = 1
        ctx.usage = res.usage
        await ctx.deps.guard.add_cost(res.usage.cost_usd(s.assistant_model))

    ctx.reason = res.reason
    match res.kind:
        case "TOOLS":
            if _needs_auth(ctx, res.calls):
                ctx.session.auth_pending = AuthPending(state["question"], res.calls)
                _ask_auth(ctx, res.calls)
            else:
                ctx.route = "TOOL"
        case "REJECT":
            ctx.route = "REJECT"
            ctx.reply = replies.REJECT_TEXT.get(res.reason or "", replies.REJECT_TEXT["OUT_OF_SCOPE"])
        case "ASK_USER":
            ctx.route = "ASK_USER"
            ctx.reply = replies.ASK_TEXT.get(res.reason or "", replies.ASK_TEXT["STOCK"])
        case "NO_TOOL" | "REFUSAL":
            ctx.route = "ERROR"
            ctx.reply = replies.REJECT_TEXT["OUT_OF_SCOPE"]
        case _:
            ctx.route = "ERROR"
            ctx.reply = replies.LLM_ERROR
    return {"route": ctx.route, "calls": [{"name": c.name, "args": c.args} for c in res.calls]}


async def execute(state: ChatState) -> ChatState:
    await run_tools_and_send_cards(_ctx(), _calls(state))
    return {}


def after_guard(state: ChatState) -> str:
    return {"PICK": "execute", "RESUME": "execute", "INTERPRET": "interpret"}.get(state.get("route", ""), "end")


def after_interpret(state: ChatState) -> str:
    return "execute" if state.get("route") == "TOOL" else "end"
