"""대화의 조회 날짜 상태 (2026-10-18). 모델에 맡기지 않고 코드로 고정한다.

날짜 값은 의미값이다 (2026-10-20): "오늘" → TODAY, "어제" → YESTERDAY, 그 밖의 날짜 → YYYY-MM-DD.
시장별 실제 날짜(미국 "오늘" = 최근 미국 장 등)는 Kotlin AssistantDate 가 정한다. 이 모듈은 시장을 보지 않는다.

규칙 (날짜를 받는 조회 도구에만 적용):
- 질문에 날짜 표현("10월 15일", "어제", "오늘", "금요일" 등)이 있으면 모델이 넣은 값으로 상태를 바꾼다
- "최근", "지금", "현재"가 있으면 상태를 비운다 → 이후 질문은 최근 거래일
- "그날", "같은 날"은 저장된 값을 그대로 쓴다
- 날짜 표현이 없으면 저장된 값을 쓴다 (모델이 날짜를 넣었든 뺐든 상태대로 맞춘다).
  저장된 값이 없으면 날짜 없이(최근)
- 저장된 값을 이어받아 조회하면 "앞 질문과 같은 ○○ 기준" 안내를 띄운다
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.chat.session import ChatSession, ToolCall

SLOT = "date"

TODAY = "TODAY"
YESTERDAY = "YESTERDAY"

# date 인자를 받는 조회 도구 (registry 와 맞춘다). 브리핑 이동·일정은 제외
DATED_TOOLS = {
    "get_market_summary", "get_circuit_breakers", "get_stock_quote", "get_stock_investor_flow",
    "get_market_investor_flow", "get_recommend_list", "get_treasury_yields", "get_trading_rank",
}

_WEEKDAYS = "월화수목금토일"

_RESET = re.compile(r"최근|지금|현재")
_SAME_DAY = re.compile(r"그\s?날|같은\s?날|그때|당일")
_EXPLICIT = re.compile(
    r"\d{1,2}\s*월\s*\d{1,2}\s*일|\d{1,2}\s*일(?![간치])|\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}/\d{1,2}"
    r"|오늘|어제|그제|그저께|엊그제|내일|모레|전날|다음\s?날"
    r"|지난\s?주|저번\s?주|이번\s?주|[월화수목금토일]요일"
)
_TODAY_WORD = re.compile(r"오늘")
_YESTERDAY_WORD = re.compile(r"어제")


def _label(v: str) -> str:
    if v == TODAY:
        return "오늘"
    if v == YESTERDAY:
        return "어제"
    try:
        d = date.fromisoformat(v)
    except ValueError:
        return v  # 형식 오류는 Kotlin 이 거절한다
    return f"{d.month}/{d.day}({_WEEKDAYS[d.weekday()]})"


def _normalize(value: str, question: str, today: date) -> str:
    """모델 값 정리. 지시와 달리 "오늘"·"어제"를 날짜로 계산해 넣었으면 의미값으로 되돌린다"""
    v = value.strip()
    if v.upper() in (TODAY, YESTERDAY):
        return v.upper()
    if v == today.isoformat() and _TODAY_WORD.search(question):
        return TODAY
    if v == (today - timedelta(days=1)).isoformat() and _YESTERDAY_WORD.search(question):
        return YESTERDAY
    return v


def apply_date_context(
    question: str, calls: list[ToolCall], session: ChatSession, today: date | None = None
) -> tuple[list[ToolCall], str | None]:
    """도구 호출의 date 를 대화 상태에 맞추고 상태를 갱신한다. 이어받았으면 안내 문장을 돌려준다"""
    dated = [c for c in calls if c.name in DATED_TOOLS]
    if not dated:
        return calls, None  # 날짜와 무관한 조회 — 상태 유지

    stored = session.slots.get(SLOT)
    if _RESET.search(question):
        target, inherited = None, False
    elif _SAME_DAY.search(question):
        target, inherited = stored, stored is not None
    elif _EXPLICIT.search(question):
        raw = next((str(c.args["date"]) for c in dated if c.args.get("date")), None)  # 모델이 넣은 값
        target = _normalize(raw, question, today or date.today()) if raw else None
        inherited = False
    else:
        target, inherited = stored, stored is not None

    if target:
        session.slots[SLOT] = target
    else:
        session.slots.pop(SLOT, None)

    out = []
    for c in calls:
        if c.name not in DATED_TOOLS:
            out.append(c)
            continue
        args = {k: v for k, v in c.args.items() if k != "date"}
        if target:
            args["date"] = target
        out.append(ToolCall(c.name, args))
    notice = f"앞 질문과 같은 {_label(target)} 기준입니다." if inherited and target else None
    return out, notice
