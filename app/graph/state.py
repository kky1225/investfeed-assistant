"""그래프 상태. 질문·라우트·도구명·카드 참조만 담는다. 개인 데이터(보유·잔고·금액)는 넣지 않는다 (C-01)."""

from typing import TypedDict


class AssistantState(TypedDict, total=False):
    member_id: int
    question: str
    route: str  # SMALLTALK | FEATURE | REJECT (2단계 이후 분류)
    capability: str | None  # 도구 이름
    tool_result: str | None  # 데이터 도구 결과(공개 데이터) 또는 카드 참조 ID
    answer: str
    verified: bool
