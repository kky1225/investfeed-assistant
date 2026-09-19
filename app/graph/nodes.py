"""5노드 스텁 (명세 3.1). 1단계는 전부 통과하고 질문을 그대로 돌려준다. LLM 호출 없음."""

from app.graph.state import AssistantState


def guard(state: AssistantState) -> AssistantState:
    return {"route": "FEATURE"}


def classify(state: AssistantState) -> AssistantState:
    return {"capability": None}


def capability(state: AssistantState) -> AssistantState:
    return {}


def execute(state: AssistantState) -> AssistantState:
    return {"answer": f"(준비 중) 받은 질문: {state.get('question', '')}"}


def verify(state: AssistantState) -> AssistantState:
    return {"verified": True}
