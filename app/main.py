from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import CurrentPrincipal
from app.auth.jwks import JwksVerifier, http_fetcher
from app.config import get_settings
from app.graph.build import build_graph, make_checkpointer
from app.tools.core_client import CoreClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("assistant")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.verifier = JwksVerifier(
        http_fetcher(s.core_jwks_url), s.token_issuer, s.token_audience, s.jwks_cache_seconds
    )
    app.state.graph = build_graph(make_checkpointer(s.redis_url))
    app.state.core = CoreClient(s.core_internal_base_url, s.core_timeout_seconds)
    yield
    await app.state.core.aclose()


app = FastAPI(title="investfeed-assistant", lifespan=lifespan)


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


@app.get("/assistant/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/assistant/chat")
async def chat(req: ChatReq, principal: CurrentPrincipal):
    """1단계 스텁: 그래프를 통과시킨 뒤 답변을 SSE 로 흘려보낸다. LLM 호출 없음."""
    session_id = req.session_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": f"{principal.member_id}:{session_id}"}}
    result = app.state.graph.invoke({"member_id": principal.member_id, "question": req.message}, config=config)

    async def stream():
        yield {"event": "meta", "data": json.dumps({"sessionId": session_id, "memberId": principal.member_id})}
        yield {"event": "token", "data": result.get("answer", "")}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(stream())
