"""도구 레지스트리 타입 (명세 3.2). 1단계는 타입만.

데이터 도구는 공개 데이터 JSON, 표시 도구는 카드 참조 ID 만 반환한다.
"""

from dataclasses import dataclass
from enum import StrEnum


class ToolKind(StrEnum):
    DATA = "DATA"
    DISPLAY = "DISPLAY"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: ToolKind
    path: str  # Kotlin /internal/assistant/tools/<name>
    description: str


REGISTRY: dict[str, ToolSpec] = {
    "get_stock_quote": ToolSpec(
        "get_stock_quote", ToolKind.DATA, "/internal/assistant/tools/get_stock_quote", "종목 현재가·등락"
    ),
}
