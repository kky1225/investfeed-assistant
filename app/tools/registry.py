"""도구 레지스트리 (명세 3.2, 4단계 확정본 — 데이터 11 · 표시 4 · 실행 1.
이후 추가: get_trading_rank 2026-10-19, get_sector_performance 2026-10-24).

5단계 해석 노드가 이 목록을 그대로 모델에 넘긴다(Anthropic tool 형식, strict). 인자 검증은 스키마(required·enum)가 맡고,
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
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False}
    )
    # strict 는 요청 전체에서 선택 인자 합계가 STRICT_OPTIONAL_LIMIT 이하여야 한다 (넘으면 API 400).
    # 선택 인자가 많고 값 검증을 Kotlin 이 하는 도구만 False 로 둔다
    strict: bool = True

    def to_anthropic(self) -> dict[str, Any]:
        """수치·길이·배열 제약은 strict 가 지원하지 않는다. 범위 검사는 Kotlin 이 한다 (DataToolService 상수)"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": strip_unsupported(self.input_schema),
            "strict": self.strict,
        }

    def optional_count(self) -> int:
        required = set(self.input_schema.get("required", []))
        return sum(1 for k in self.input_schema.get("properties", {}) if k not in required)


STRICT_OPTIONAL_LIMIT = 24


# strict 스키마가 지원하지 않는 키 (Anthropic 구조화 출력 제한)
_UNSUPPORTED = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems"}


def strip_unsupported(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: strip_unsupported(v) for k, v in schema.items() if k not in _UNSUPPORTED}
    if isinstance(schema, list):
        return [strip_unsupported(v) for v in schema]
    return schema


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


# 인자 범위의 기준은 Kotlin DataToolService 상수(MAX_STOCKS 등)다. 여기 설명 문구의 숫자("1~3개" 등)는
# 모델이 인자를 고르는 안내일 뿐이니, Kotlin 값을 바꾸면 문구도 같이 바꾼다 (2026-10-04, Python 범위 검사 제거).
_STOCK_QUERY = {"type": "string", "description": "종목명·별칭·코드·티커 (삼성전자, 삼전, 005930, TLT, 비트코인)"}
_STOCK_QUERIES = {
    "type": "array",
    "items": _STOCK_QUERY,
    "description": "종목 1~3개. 비교 질문이면 여러 개",
}
_MARKET_HINT = {"type": "string", "enum": ["KR", "US", "CRYPTO"], "description": "질문에서 시장이 분명할 때만"}
_ASSET_CLASS = {
    "type": "string",
    "enum": ["KR", "US", "CRYPTO"],
    "description": "국내주식/미국주식/코인. 미지정이면 전체",
}

# 날짜 지정 조회 공통 인자. 미지정이면 서버가 오늘(장 전·휴장일이면 직전 거래일)로 답한다.
# 오늘·어제는 날짜를 계산하지 않고 의미값으로 넘긴다 — 시장별 실제 날짜는 Kotlin AssistantDate 가 정한다 (2026-10-20).
# union(anyOf·enum) 은 strict 한도에 걸려 문자열 하나로 받고 값 검증은 Kotlin
_DATE = {
    "type": "string",
    "description": "질문에 날짜가 있을 때만. '오늘' → TODAY, '어제' → YESTERDAY, "
    "그 밖의 날짜('10월 15일', '그제', '지난주 금요일')는 YYYY-MM-DD. '지금'·'현재'·'최근'이거나 날짜가 없으면 비운다",
}

_SPECS: list[ToolSpec] = [
    # ── 데이터 도구 ──
    ToolSpec(
        "get_market_summary",
        ToolKind.DATA,
        "/internal/assistant/tools/get_market_summary",
        "국내 지수 값·등락과 외국인/기관/개인 순매수. 날짜를 주면 그날 종가·수급. "
        "예: '코스피 지금 얼마야', '코스닥 수급', '국내 지수 몇이야', '오늘 장 어땠어', '10월 15일 코스피'",
        _obj(
            {
                "market": {
                    "type": "string",
                    "enum": ["KOSPI", "KOSDAQ"],
                    "description": "코스피만 물으면 KOSPI, 코스닥만 물으면 KOSDAQ. "
                    "'국내 지수', '오늘 장'처럼 시장을 특정하지 않으면 비운다(둘 다)",
                },
                "date": _DATE,
            }
        ),
    ),
    ToolSpec(
        "get_circuit_breakers",
        ToolKind.DATA,
        "/internal/assistant/tools/get_circuit_breakers",
        "서킷브레이커(시장 전체 매매 정지) 발동 여부. 국내는 오늘(휴장일이면 직전 거래일) 코스피·코스닥, "
        "미국은 진행 중이거나 직전 미국 장의 S&P500 기준 시장 전체(나스닥 단독 서킷브레이커는 없음). "
        "예: '서킷브레이커 걸렸어', '오늘 코스피 서킷브레이커 발동했어', '10월 15일 코스피 서킷브레이커', "
        "'미국 서킷브레이커 걸렸어'",
        _obj(
            {
                "market": {
                    "type": "string",
                    "enum": ["KR", "US"],
                    "description": "국내=KR(코스피·코스닥), 미국=US(나스닥·S&P500·다우 모두 US). "
                    "질문·대화 맥락에 시장이 없으면 추측하지 말고 ask_user(MARKET)",
                },
                "index": {
                    "type": "string",
                    "enum": ["KOSPI", "KOSDAQ", "SP500", "NASDAQ", "DOW"],
                    "description": "질문에 지수를 직접 말했을 때만 (코스피·코스닥·S&P500·나스닥·다우). "
                    "미지정이면 생략. 지수를 말해도 market 은 반드시 함께 지정",
                },
                "date": _DATE,
            },
            ["market"],
        ),
    ),
    ToolSpec(
        "get_market_investor_flow",
        ToolKind.DATA,
        "/internal/assistant/tools/get_market_investor_flow",
        "투자자별(외국인·기관·연기금·개인) 순매수/순매도 상위 종목 순위. "
        "코스피+코스닥 전체 (투자자별 목록 화면과 같음). "
        "기간 누적·날짜 지정 가능, 외국인·기관은 연속 순매수 일수 조건 가능. "
        "예: '오늘 외인 뭐 샀어', '최근 5일 기관 순매도 상위', '외인이 3일 연속 산 종목', '10월 15일 외인 순매수'",
        _obj(
            {
                "investor": {
                    "type": "string",
                    "enum": ["FOREIGN", "INSTITUTION", "PENSION", "INDIVIDUAL"],
                    "description": "질문·맥락에 투자자가 없으면 추측하지 말고 ask_user(INVESTOR)",
                },
                "days": {
                    "type": "integer",
                    "enum": [1, 3, 5, 10, 20],
                    "description": "기간(거래일). '오늘'=1, '최근 일주일'=5",
                },
                "side": {
                    "type": "string",
                    "enum": ["BUY", "SELL"],
                    "description": "순매수=BUY('샀어', '매수'), 순매도=SELL('팔았어', '매도'). "
                    "질문·맥락으로 알 수 없으면 추측하지 말고 ask_user(SIDE)",
                },
                "minStreakDays": {
                    "type": "integer",
                    "description": "'N일 연속' 조건(2~20일). 외국인·기관만",
                },
                "date": {
                    **_DATE,
                    "description": _DATE["description"] + ". 그날까지 거슬러 days 거래일 집계",
                },
            },
            ["investor", "side"],
        ),
        strict=False,  # 선택 인자가 많아 strict 한도(24) 때문에 해제, 값 검증은 Kotlin
    ),
    ToolSpec(
        "get_trading_rank",
        ToolKind.DATA,
        "/internal/assistant/tools/get_trading_rank",
        "거래대금·거래량·거래량 급증률 상위 종목 순위 (순위 화면과 같음). 국내(코스피+코스닥) 또는 미국. "
        "당일 순위만 있고 지난 날짜는 서버가 안내한다. "
        "예: '거래대금 상위', '오늘 거래량 많은 종목', '미국 거래량 급증', '거래 많이 터진 종목'",
        _obj(
            {
                "market": {
                    "type": "string",
                    "enum": ["KR", "US"],
                    "description": "국내=KR, 미국=US. 질문·대화 맥락에 시장이 없으면 추측하지 말고 ask_user(MARKET)",
                },
                "type": {
                    "type": "string",
                    "enum": ["VALUE", "VOLUME", "SURGE"],
                    "description": "거래대금=VALUE, 거래량=VOLUME, 거래량 급증(률)=SURGE. "
                    "'거래 많은'처럼 대금·거래량을 가리지 않으면 VALUE. "
                    "'순위 보여줘'처럼 종류가 없으면 ask_user(RANK_TYPE)",
                },
                "date": _DATE,
            },
            ["market", "type"],
        ),
    ),
    ToolSpec(
        "get_sector_performance",
        ToolKind.DATA,
        "/internal/assistant/tools/get_sector_performance",
        "업종별 당일 등락률 (업종 화면 히트맵과 같음). 국내는 코스피·코스닥 산업 업종, 미국은 업종 41개. "
        "업종을 주면 그 업종의 소속 종목. 당일 값만 있고 지난 날짜·기간 수익률은 서버가 안내한다. "
        "종목이 어느 업종인지 묻는 질문에는 쓰지 않는다(reject UNSUPPORTED). "
        "예: '오늘 업종 어때', '코스닥 업종', '많이 내린 업종', '거래대금 몰린 업종', '반도체 업종 어때', "
        "'코스닥 화학 업종', '미국 업종 한 달 수익률'",
        _obj(
            {
                "market": {
                    "type": "string",
                    "enum": ["KR", "KOSPI", "KOSDAQ", "US"],
                    "description": "코스피만=KOSPI, 코스닥만=KOSDAQ, '국내'처럼 둘을 가리지 않으면 KR(둘 다), 미국=US. "
                    "국내인지 미국인지 질문·대화 맥락에 없으면 추측하지 말고 ask_user(MARKET)",
                },
                "sector": {
                    "type": "string",
                    "description": "업종을 말했을 때만. 사용자가 쓴 그대로 (반도체, 전기전자, 은행, 화학). "
                    "업종 확정은 서버가 한다",
                },
                "multiDay": {
                    "type": "boolean",
                    "description": "'일주일', '한 달', '올해'처럼 여러 날에 걸친 수익률을 물으면 true. "
                    "그 밖에는 비운다",
                },
                "sort": {
                    "type": "string",
                    "enum": ["RISE", "FALL", "VALUE"],
                    "description": "정렬: 많이 내린·약한·하락=FALL, 거래대금·거래 많은·돈 몰린=VALUE. "
                    "많이 오른·강한·순위만 물으면 비운다(등락률 높은 순)",
                },
                "date": _DATE,
            },
            ["market"],
        ),
    ),
    ToolSpec(
        "get_stock_quote",
        ToolKind.DATA,
        "/internal/assistant/tools/get_stock_quote",
        "종목 시세: 현재가·등락·거래량·당일 고저·52주 고저. 국내·미국·코인. 종목 2~3개면 비교. "
        "날짜를 주면 그날 종가·고저·거래량. "
        "예: '삼성전자 얼마야', 'TLT 현재가', '비트코인 시세', '삼성전자랑 하이닉스 비교', '10월 15일 삼성전자 종가'",
        _obj({"stockQuery": _STOCK_QUERIES, "market": _MARKET_HINT, "date": _DATE}, ["stockQuery"]),
    ),
    ToolSpec(
        "get_stock_investor_flow",
        ToolKind.DATA,
        "/internal/assistant/tools/get_stock_investor_flow",
        "국내 종목의 일자별 외국인/기관/개인 순매수(금액)와 연속 순매수 일수. "
        "예: '삼성전자 외인 수급', '하이닉스 기관 며칠 연속 샀어', '10월 15일 삼성전자 수급'",
        _obj(
            {
                "stockQuery": _STOCK_QUERIES,
                "days": {
                    "type": "integer",
                    "description": "최근 며칠(1~10). 미지정 5. date 가 있으면 그날까지 거슬러 며칠",
                },
                "date": _DATE,
            },
            ["stockQuery"],
        ),
    ),
    ToolSpec(
        "get_global_indexes",
        ToolKind.DATA,
        "/internal/assistant/tools/get_global_indexes",
        "미국 지수(나스닥·S&P500·다우·필라델피아 반도체)·미국 국채 2/5/10/30년·환율 당일 스냅샷. "
        "예: '미국장 어때', '환율'. 과거 날짜 조회 불가 — 국채만 날짜를 물으면 get_treasury_yields",
    ),
    ToolSpec(
        "get_treasury_yields",
        ToolKind.DATA,
        "/internal/assistant/tools/get_treasury_yields",
        "국채 금리: 한국 2/3/5/10/20/30년, 미국 2/5/10/30년. 날짜를 주면 그날 종가. "
        "예: '국채 금리', '한국 국채 10년', '미국 국채 금리', '10월 15일 미국 국채'",
        _obj(
            {
                "market": {
                    "type": "string",
                    "enum": ["KR", "US"],
                    "description": "한국 국채=KR, 미국 국채=US. '국채 금리'처럼 특정하지 않으면 비운다(둘 다)",
                },
                "date": _DATE,
            }
        ),
    ),
    ToolSpec(
        "get_calendar",
        ToolKind.DATA,
        "/internal/assistant/tools/get_calendar",
        "경제 일정(지표 발표·금리 결정·휴장). "
        "예: '이번 주 일정', 'FOMC 언제야', '다음 달 CPI 발표일', '이번 달 휴장일', '미국 증시 쉬는 날'",
        _obj(
            {
                "from": {"type": "string", "format": "date", "description": "YYYY-MM-DD"},
                "to": {"type": "string", "format": "date", "description": "YYYY-MM-DD. 최대 3개월"},
                "keyword": {
                    "type": "string",
                    "description": "이벤트명 부분 일치 (FOMC, CPI). 휴장·금리 결정은 type 으로",
                },
                "type": {
                    "type": "string",
                    "enum": ["INDICATOR", "HOLIDAY", "MEETING"],
                    "description": "INDICATOR=지표 발표(CPI·고용·GDP), HOLIDAY=휴장일, MEETING=금리 결정(FOMC·금통위)",
                },
                "country": {"type": "string", "enum": ["KR", "US"], "description": "국내/미국. 질문에 있을 때만"},
            },
            ["from", "to"],
        ),
    ),
    ToolSpec(
        "get_recommend_list",
        ToolKind.DATA,
        "/internal/assistant/tools/get_recommend_list",
        "오늘의 시스템 분류(추천) 종목 목록 — 등급별 종목명. "
        "날짜를 주면 그날 산출한 추천 기록. "
        "예: '오늘 추천 뭐야', 'BUY 종목', '삼성전자 등급'(목록에 있으면), '10월 15일 추천'",
        _obj(
            {
                "grade": {
                    "type": "string",
                    "enum": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"],
                    "description": "미지정이면 전체",
                },
                "date": _DATE,
            }
        ),
    ),
    ToolSpec(
        "search_news",
        ToolKind.DATA,
        "/internal/assistant/tools/search_news",
        "뉴스 검색 (제목·날짜·링크, 최대 5건). 예: '삼성전자 뉴스', '반도체 뉴스 있어'",
        _obj({"query": {"type": "string"}, "n": {"type": "integer", "description": "개수(1~5). 미지정 5"}}, ["query"]),
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
        strict=False,  # 선택 인자 5개 — strict 한도(24) 때문에 해제, 값 검증은 Kotlin
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
                "price": {"type": "integer", "description": "목표가 (원, 0보다 큼)"},
                "direction": {"type": "string", "enum": ["ABOVE", "BELOW"], "description": "이상/이하 도달"},
            },
            ["stockQuery", "price", "direction"],
        ),
    ),
]

REGISTRY: dict[str, ToolSpec] = {t.name: t for t in _SPECS}


def requires_personal(name: str) -> bool:
    """개인 도구(표시·실행)인가 — 2차 인증 토큰이 있어야 실행한다. Kotlin ServiceTokenFilter 도 같은 기준으로 막는다"""
    spec = REGISTRY.get(name)
    return spec is not None and spec.kind != ToolKind.DATA


def _check_strict_budget() -> None:
    total = sum(t.optional_count() for t in _SPECS if t.strict)
    if total > STRICT_OPTIONAL_LIMIT:
        raise RuntimeError(f"strict 선택 인자 {total}개 > 한도 {STRICT_OPTIONAL_LIMIT}: 일부 도구를 strict=False 로")


_check_strict_budget()


def anthropic_tools() -> list[dict[str, Any]]:
    """5단계 해석 노드용 — 모델에 넘길 도구 목록"""
    return [t.to_anthropic() for t in _SPECS]
