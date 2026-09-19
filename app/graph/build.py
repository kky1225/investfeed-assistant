from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import AssistantState

log = logging.getLogger(__name__)

CHECKPOINT_PREFIX = "ASSIST:CKPT"


def make_checkpointer(redis_url: str) -> BaseCheckpointSaver:
    """Redis 체크포인터. Redis Stack(RedisJSON·RediSearch) 이 없으면 메모리로 대체하고 경고를 남긴다."""
    try:
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(redis_url=redis_url)
        saver.setup()
        return saver
    except Exception as e:  # noqa: BLE001 - 인프라 부재는 서비스 기동을 막지 않는다
        log.warning("Redis 체크포인터 사용 불가(%s) → MemorySaver 로 대체", e)
        return MemorySaver()


def build_graph(checkpointer: BaseCheckpointSaver):
    g = StateGraph(AssistantState)
    g.add_node("guard", nodes.guard)
    g.add_node("classify", nodes.classify)
    g.add_node("capability", nodes.capability)
    g.add_node("execute", nodes.execute)
    g.add_node("verify", nodes.verify)
    g.add_edge(START, "guard")
    g.add_edge("guard", "classify")
    g.add_edge("classify", "capability")
    g.add_edge("capability", "execute")
    g.add_edge("execute", "verify")
    g.add_edge("verify", END)
    return g.compile(checkpointer=checkpointer)
