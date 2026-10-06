"""그래프 상태. 질문·라우트·도구 호출(이름·인자)만 담는다. 도구 결과·카드·개인 데이터는 넣지 않는다 (C-01).

카드는 턴 문맥(app.chat.context.TurnContext)에만 있고 턴이 끝나면 버린다.
"""

from typing import Any, TypedDict


class ChatState(TypedDict, total=False):
    member_id: int
    question: str
    pick: dict[str, Any] | None  # 종목 선택 {code, market, name}
    route: str  # INTERPRET / TOOL / REJECT / ASK_USER / PICK / BLOCKED / ERROR
    calls: list[dict[str, Any]]  # [{name, args}]
