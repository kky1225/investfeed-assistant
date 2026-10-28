"""도구 실행 — Kotlin /internal 호출을 병렬로 하고 끝나는 대로 카드를 흘려보낸다.

데이터·실행 도구는 payload, 표시 도구는 카드 참조(ref) 만 다룬다 (C-01). 결과는 LLM 에 돌려주지 않는다.
종목 후보가 여럿이면 선택 카드를 보내고 해당 도구 호출을 세션 pending 에 둔다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.chat.context import TurnContext
from app.chat.session import Pending, PendingItem, ToolCall
from app.tools.core_client import ToolResult
from app.tools.registry import REGISTRY

log = logging.getLogger(__name__)

STOCK_CHOICE = "STOCK_CHOICE"


def to_card(call: ToolCall, result: ToolResult) -> dict[str, Any]:
    """Kotlin 도구 응답 → 화면 카드. 실패는 error, 개인 데이터는 ref(React 가 Kotlin 에서 직접 조회), 공개 데이터는 payload"""
    base = {"asOf": result.as_of, "source": result.source}
    if not result.ok:
        return {"kind": call.name, "error": result.error or "조회에 실패했습니다", **base}
    if isinstance(result.data, dict) and "cardRef" in result.data:
        return {"kind": result.data.get("kind") or call.name, "ref": result.data["cardRef"], **base}
    # 공개 데이터 카드에는 조회 조건(도구 인자)도 붙인다
    # 화면이 "미국 휴장일 없음"처럼 조건 기준 안내를 할 수 있게 (2026-10-01)
    return {"kind": call.name, "payload": result.data, "args": call.args, **base}


async def run_tools_and_send_cards(ctx: TurnContext, calls: list[ToolCall]) -> None:
    """도구들을 동시에 실행하고, 끝나는 대로 카드를 화면에 보낸다. 종목 후보가 여럿인 호출은 모아서 마지막에 되묻는다"""
    ambiguous_results: list[tuple[ToolCall, ToolResult]] = []  # 종목 후보가 여럿이라 보류된 (호출, 응답)

    async def call_tool_and_send_card(call: ToolCall) -> None:
        """도구 하나: Kotlin 도구 API 호출 → 카드로 바꿔 즉시 전송 (후보가 여럿이면 보류)"""
        ctx.tool_names.append(call.name)
        if REGISTRY.get(call.name) is None:
            ctx.tool_errors += 1
            ctx.add_card({"kind": call.name, "error": "지원하지 않는 조회입니다"})
            return
        try:
            result = await ctx.deps.core.call(ctx.token, call.name, call.args)
        except httpx.HTTPError as e:
            log.error("도구 호출 실패 tool=%s request=%s: %s", call.name, ctx.request_id, type(e).__name__)
            result = ToolResult(ok=False, error="조회에 실패했습니다")
        if not result.ok and result.candidates:
            ambiguous_results.append((call, result))
            return
        if not result.ok:
            ctx.tool_errors += 1
        # 문장으로 답하는 결과 ("발동하지 않았습니다", "휴장일입니다" 등) — Kotlin 이 data.reply 로 문장을 준다.
        # 다른 카드와 함께 와도 사라지지 않게 카드로 흘려보내고(화면은 말풍선으로 그림), 저장 문장에도 이어 붙인다
        # 카드와 함께 오는 안내(notice, 예: 여러 종목 중 미국만 휴장)도 저장 문장에 남긴다
        data = result.data if result.ok and isinstance(result.data, dict) else {}
        if text := data.get("reply") or data.get("notice"):
            ctx.reply = f"{ctx.reply}\n{text}" if ctx.reply else text
        ctx.add_card(to_card(call, result))

    # 호출마다 작업을 만들어 동시에 실행하고, 전부 끝날 때까지 기다린다
    await asyncio.gather(*(call_tool_and_send_card(call) for call in calls))

    # 후보 되묻기는 한 번에 검색어 하나. 같은 검색어로 후보가 난 호출만 이번 선택으로 바꾸고,
    # 다른 검색어의 호출(이전 선택에서 넘어온 것 포함)은 later 에 두어 다음 차례에 묻는다
    pending_items = [
        PendingItem(call, result.query or "", result.candidates or []) for call, result in ambiguous_results
    ] + ctx.carried
    if pending_items:
        query, candidates = pending_items[0].query, pending_items[0].candidates
        ctx.session.pending = Pending(
            [item.call for item in pending_items if item.query == query], query, candidates,
            [item for item in pending_items if item.query != query],
        )
        ctx.add_card({"kind": STOCK_CHOICE, "payload": {"query": query, "candidates": candidates}})


def apply_stock_choice(calls: list[ToolCall], query: str, value: str, market: str | None) -> list[ToolCall]:
    """사용자가 고른 종목(value)을 보류된 호출의 검색어(query) 자리에 넣는다.

    calls 는 이 query 로 후보를 낸 호출만 들어온다 (Pending.calls). 그래서 표기 차이로 일치하는 인자가 없어도
    종목 인자가 하나면 그것이 곧 query 다. 다른 검색어의 호출은 Pending.later 에 있어 여기 오지 않는다.
    """
    out = []
    for call in calls:
        args = dict(call.args)
        stock_query = args.get("stockQuery")
        if isinstance(stock_query, list):  # 여러 종목 도구(시세·수급): 검색어와 같은 항목만 교체
            replaced = [value if str(x).strip().casefold() == query.strip().casefold() else x for x in stock_query]
            if replaced == stock_query and len(stock_query) == 1:
                replaced = [value]
            args["stockQuery"] = replaced
        elif stock_query is not None:  # 단일 종목 도구 (보유 종목·목표가 알림)
            args["stockQuery"] = value
        spec = REGISTRY.get(call.name)
        # 고른 종목의 시장도 지정 — 국내·미국에 같은 이름이 있어도 재실행 때 다시 애매해지지 않게
        if market and spec and "market" in spec.input_schema.get("properties", {}):
            args["market"] = market
        out.append(ToolCall(call.name, args))
    return out
