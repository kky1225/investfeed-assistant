from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import CurrentPrincipal
from app.auth.jwks import SCOPE_PERSONAL, JwksVerifier, http_fetcher
from app.chat.context import Deps, TurnContext
from app.chat.guard import Guard
from app.chat.session import SessionStore
from app.chat.turn import run_turn
from app.config import get_settings
from app.graph.build import build_graph
from app.tools.core_client import CoreClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("assistant")


# FastAPI(lifespan=...) 에 등록 → yield 앞은 서버 시작 시(요청 받기 전) 1회, yield 뒤는 종료 시 1회 실행
@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.verifier = JwksVerifier(
        http_fetcher(s.core_jwks_url), s.token_issuer, s.token_audience, s.jwks_cache_seconds
    )
    redis = Redis.from_url(s.redis_url, decode_responses=True)
    core = CoreClient(s.core_internal_base_url, s.core_timeout_seconds)
    app.state.deps = Deps(
        settings=s,
        core=core,
        llm=anthropic.AsyncAnthropic(
            api_key=s.anthropic_api_key or None, timeout=s.llm_timeout_seconds, max_retries=1
        ),
        store=SessionStore(redis, s.session_ttl_seconds),
        guard=Guard(redis, s.rate_per_minute, s.monthly_cost_cap_usd),
    )
    app.state.graph = build_graph()
    app.state.tasks = set()  # 백그라운드 턴 참조 유지
    yield
    await core.aclose()
    await redis.aclose()


app = FastAPI(title="investfeed-assistant", lifespan=lifespan)


class PickReq(BaseModel):
    """종목 후보 선택 — LLM 재호출 없이 대기 중 도구 호출을 재실행"""

    code: str = Field(min_length=1, max_length=20)
    market: str | None = Field(default=None, pattern="^(KR|US|CRYPTO)$")
    name: str | None = Field(default=None, max_length=100)


class GroupPickReq(BaseModel):
    """관심종목 그룹 선택 — LLM 재호출 없이 고른 그룹의 종목 카드를 조회 (그룹 소유 확인은 Kotlin)"""

    groupId: int = Field(gt=0)
    kind: str = Field(pattern="^(STOCK|CRYPTO)$")
    name: str | None = Field(default=None, max_length=100)


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    pick: PickReq | None = None
    group: GroupPickReq | None = None
    resume: bool = False  # 2차 인증 후 이어서 실행 — 대기 중 도구 호출을 LLM 재호출 없이 실행


@app.get("/assistant/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/assistant/chat")
# principal: CurrentPrincipal → FastAPI 가 이 함수 실행 전에 auth/deps.current_principal(토큰 검증)을 먼저 돌려 채운다.
# 검증 실패면 401 로 끝나 이 함수는 실행되지 않는다. 후보 카드 클릭이면 req.pick 이 들어온다(입력 질문은 None)
async def chat(req: ChatReq, principal: CurrentPrincipal):
    """질문 1턴. 실행은 백그라운드 작업이라 SSE 가 끊겨도 턴 저장까지 끝난다"""
    deps: Deps = app.state.deps
    request_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    ctx = TurnContext(
        deps=deps,
        member_id=principal.member_id,
        token=principal.token,
        personal=principal.scope == SCOPE_PERSONAL,
        request_id=request_id,
        question=req.message.strip(),
        session=await deps.store.load(principal.member_id),
        queue=queue,
    )
    pick = req.pick.model_dump() if req.pick else None
    group = req.group.model_dump() if req.group else None
    # 처리(run_turn)는 SSE 연결과 분리된 백그라운드 작업 — 처리 쪽이 큐에 이벤트를 넣고, 아래 stream() 이 꺼내 보낸다
    task = asyncio.create_task(run_turn(app.state.graph, deps, ctx, pick, req.resume, group))
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)

    async def stream():
        yield {"event": "meta", "data": json.dumps({"requestId": request_id})}
        while (item := await queue.get()) is not None:
            event, data = item
            yield {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}

    return EventSourceResponse(stream())
