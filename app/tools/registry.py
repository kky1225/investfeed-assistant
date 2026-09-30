"""도구 레지스트리 (명세 3.2, 4단계 확정본 — 데이터 7 · 표시 4 · 실행 1).

5단계 해석 노드가 이 목록을 그대로 모델에 넘긴다(Anthropic tool 형식). 인자 검증은 스키마(required·enum)가 맡고,
값 검증·종목명 확정은 Kotlin 이 한다. 데이터 도구는 공개 데이터 JSON, 표시 도구는 카드 참조 ID 만 돌려준다 (C-01).
LLM 문장 생성은 없다 — 도구 선택만 (A안, 2026-09-28).
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolKind(StrEnum):
    DATA = "DATA"  # 공개 데이터, 결과 전체 반환
    DISPLAY = "DISPLAY"  # 개인 데이터, 카드 참조만
    ACTION = "ACTION"  # 설정 변경, 확인 카드 → 실행 (실행은 프론트가 호출)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: ToolKind
    path: str  # Kotlin /internal/assistant/tools/<...>
    description: str  # 모델이 도구를 고르는 근거 — 예시 발화 포함
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def to_anthropic(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


_STOCK_QUERY = {"type": "string", "description": "종목명·별칭·코드·티커 (삼성전자, 삼전, 005930, TLT, 비트코인)"}
_STOCK_QUERIES = {
    "type": "array",
    "items": _STOCK_QUERY,
    "minItems": 1,
    "maxItems": 3,
    "description": "종목 1~3개. 비교 질문이면 여러 개",
}
_MARKET_HINT = {"type": "string", "enum": ["KR", "US", "CRYPTO"], "description": "질문에서 시장이 분명할 때만"}
_ASSET_CLASS = {
    "type": "string",
    "enum": ["KR", "US", "CRYPTO"],
    "description": "국내주식/미국주식/코인. 미지정이면 전체",
}

_SPECS: list[ToolSpec] = [
    # ── 데이터 도구 ──
    ToolSpec(
        "get_market_summary",
        ToolKind.DATA,
        "/internal/assistant/tools/get_market_summary",
        "국내 지수(코스피·코스닥) 현재 값·등락과 외국인/기관/개인 순매수. "
        "예: '코스피 지금 얼마야', '오늘 장 어땠어', '코스닥 수급'",
        _obj({"market": {"type": "string", "enum": ["KOSPI", "KOSDAQ"], "description": "미지정이면 KOSPI"}}),
    ),
    ToolSpec(
        "get_market_investor_flow",
        ToolKind.DATA,
        "/internal/assistant/tools/get_market_investor_flow",
        "투자자별(외국인·기관·연기금·개인) 기간 누적 순매수/순매도 상위 종목. "
        "외국인·기관은 연속 순매수 일수 조건 가능. "
        "예: '오늘 외인 뭐 샀어', '최근 5일 기관 순매도 상위', '외인이 3일 연속 산 종목'",
        _obj(
            {
                "investor": {"type": "string", "enum": ["FOREIGN", "INSTITUTION", "PENSION", "INDIVIDUAL"]},
                "market": {"type": "string", "enum": ["KOSPI", "KOSDAQ"], "description": "미지정이면 KOSPI"},
                "days": {
                    "type": "integer",
                    "enum": [1, 3, 5, 10, 20],
                    "description": "기간(거래일). '오늘'=1, '최근 일주일'=5",
                },
                "side": {"type": "string", "enum": ["BUY", "SELL"], "description": "순매수/순매도. 미지정이면 BUY"},
                "minStreakDays": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 20,
                    "description": "'N일 연속' 조건. 외국인·기관만",
                },
            },
            ["investor"],
        ),
    ),
    ToolSpec(
        "get_stock_quote",
        ToolKind.DATA,
        "/internal/assistant/tools/get_stock_quote",
        "종목 시세: 현재가·등락·거래량·당일 고저·52주 고저. 국내·미국·코인. 종목 2~3개면 비교. "
        "예: '삼성전자 얼마야', 'TLT 현재가', '비트코인 시세', '삼성전자랑 하이닉스 비교'",
        _obj({"stockQuery": _STOCK_QUERIES, "market": _MARKET_HINT}, ["stockQuery"]),
    ),
    ToolSpec(
        "get_stock_investor_flow",
        ToolKind.DATA,
        "/internal/assistant/tools/get_stock_investor_flow",
        "국내 종목의 일자별 외국인/기관/개인 순매수(금액)와 연속 순매수 일수. "
        "예: '삼성전자 외인 수급', '하이닉스 기관 며칠 연속 샀어'",
        _obj(
            {
                "stockQuery": _STOCK_QUERIES,
                "days": {"type": "integer", "minimum": 1, "maximum": 10, "description": "최근 며칠. 미지정 5"},
            },
            ["stockQuery"],
        ),
    ),
    ToolSpec(
        "get_global_indexes",
        ToolKind.DATA,
        "/internal/assistant/tools/get_global_indexes",
        "미국 지수(나스닥·S&P500·다우)·미국 국채 2/10년·환율·VIX 스냅샷. 예: '미국장 어때', '환율', '금리'",
    ),
    ToolSpec(
        "get_calendar",
        ToolKind.DATA,
        "/internal/assistant/tools/get_calendar",
        "경제 일정(지표 발표·금리 결정·휴장). 예: '이번 주 일정', 'FOMC 언제야', '다음 달 CPI 발표일'",
        _obj(
            {
                "from": {"type": "string", "format": "date", "description": "YYYY-MM-DD"},
                "to": {"type": "string", "format": "date", "description": "YYYY-MM-DD. 최대 3개월"},
                "keyword": {"type": "string", "description": "이벤트명 부분 일치 (FOMC, CPI)"},
            },
            ["from", "to"],
        ),
    ),
    ToolSpec(
        "get_recommend_list",
        ToolKind.DATA,
        "/internal/assistant/tools/get_recommend_list",
        "오늘의 시스템 분류(추천) 종목 목록 — 등급별 종목명. "
        "예: '오늘 추천 뭐야', 'BUY 종목', '삼성전자 등급'(목록에 있으면)",
        _obj(
            {
                "grade": {
                    "type": "string",
                    "enum": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"],
                    "description": "미지정이면 전체",
                }
            }
        ),
    ),
    ToolSpec(
        "search_news",
        ToolKind.DATA,
        "/internal/assistant/tools/search_news",
        "뉴스 검색 (제목·날짜·링크, 최대 5건). 예: '삼성전자 뉴스', '반도체 뉴스 있어'",
        _obj({"query": {"type": "string"}, "n": {"type": "integer", "minimum": 1, "maximum": 5}}, ["query"]),
    ),
    # ── 표시 도구 (개인 데이터 → 카드 참조) ──
    ToolSpec(
        "show_my_portfolio",
        ToolKind.DISPLAY,
        "/internal/assistant/tools/show_my_portfolio",
        "내 계좌 요약 카드: 총자산·평가손익·오늘 등락·자산군별·상하위 종목. 조건 필터 가능. "
        "예: '내 계좌 어때', '총자산', '코인만', '오늘 3% 넘게 빠진 보유 종목', '수익률 마이너스인 종목'",
        _obj(
            {
                "assetClass": _ASSET_CLASS,
                "dayRateLt": {"type": "number", "description": "오늘 등락률이 이 값 미만인 종목만 (예: -3)"},
                "dayRateGt": {"type": "number", "description": "오늘 등락률이 이 값 초과인 종목만"},
                "totalRateLt": {"type": "number", "description": "총 수익률이 이 값 미만인 종목만 (예: 0)"},
                "totalRateGt": {"type": "number", "description": "총 수익률이 이 값 초과인 종목만"},
            }
        ),
    ),
    ToolSpec(
        "show_my_holding",
        ToolKind.DISPLAY,
        "/internal/assistant/tools/show_my_holding",
        "내 보유 종목 1개 카드: 수량·평단·현재가·평가손익·오늘 등락·증권사. 예: '삼성전자 몇 주 있어', '내 TLT 수익률'",
        _obj({"stockQuery": _STOCK_QUERY}, ["stockQuery"]),
    ),
    ToolSpec(
        "show_my_pnl",
        ToolKind.DISPLAY,
        "/internal/assistant/tools/show_my_pnl",
        "실현손익 카드 (기간·자산군별·증권사별). 예: '이달 실현손익', '지난달 얼마 벌었어', '올해 코인 실현손익'",
        _obj(
            {
                "period": {"type": "string", "enum": ["THIS_MONTH", "LAST_MONTH", "THIS_YEAR"]},
                "assetClass": _ASSET_CLASS,
            },
            ["period"],
        ),
    ),
    ToolSpec(
        "show_briefing",
        ToolKind.DISPLAY,
        "/internal/assistant/tools/show_briefing",
        "타임라인의 브리핑 메시지로 이동 (일자·종류). 예: '오늘 브리핑 다시', '어제 미국 마감', '코인 마감 브리핑'",
        _obj(
            {
                "date": {"type": "string", "format": "date", "description": "YYYY-MM-DD. 미지정이면 오늘"},
                "type": {"type": "string", "enum": ["US_CLOSE", "KR_PRE", "KR_CLOSE", "KR_HOLDINGS", "COIN_DAILY"]},
            },
            ["type"],
        ),
    ),
    # ── 실행 도구 (확인 카드까지. 실행은 프론트 확인 버튼) ──
    ToolSpec(
        "create_price_alert",
        ToolKind.ACTION,
        "/internal/assistant/tools/create_price_alert/preview",
        "목표가 알림 등록 확인 카드. 국내 주식·코인. 예: '삼성전자 7만원 되면 알려줘', '비트코인 1억 밑으로 가면 알림'",
        _obj(
            {
                "stockQuery": _STOCK_QUERY,
                "price": {"type": "integer", "minimum": 1, "description": "목표가 (원)"},
                "direction": {"type": "string", "enum": ["ABOVE", "BELOW"], "description": "이상/이하 도달"},
            },
            ["stockQuery", "price", "direction"],
        ),
    ),
]

REGISTRY: dict[str, ToolSpec] = {t.name: t for t in _SPECS}


def anthropic_tools() -> list[dict[str, Any]]:
    """5단계 해석 노드용 — 모델에 넘길 도구 목록"""
    return [t.to_anthropic() for t in _SPECS]
