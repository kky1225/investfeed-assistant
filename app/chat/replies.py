"""고정 응답 문구. LLM 은 문장을 쓰지 않는다 (A안) — 사용자에게 보이는 문장은 전부 여기서 나온다."""

from enum import StrEnum


class RejectReason(StrEnum):
    ACTION = "ACTION"  # 매매·행동·판단·예측 ("사도 돼", "사줘", "오를까")
    OUT_OF_SCOPE = "OUT_OF_SCOPE"  # 투자 데이터와 무관, 설명·요약 요청
    PAPER_TRADE = "PAPER_TRADE"  # 모의투자·자동매매 (관리자 전용, C-12)
    GREETING = "GREETING"  # 인사
    DATE_UNSUPPORTED = "DATE_UNSUPPORTED"  # 날짜 지정 조회를 아직 지원하지 않는 데이터
    UNSUPPORTED = "UNSUPPORTED"  # 투자 데이터 질문이지만 알맞은 도구가 없는 조회 (종목 업종 소속·재무 지표 등)
    FX_PERIOD = "FX_PERIOD"  # 환율을 여러 날(기간·추이)로 물음 — 환율은 하루 단위만 (2026-10-26)


class Missing(StrEnum):
    STOCK = "STOCK"
    PRICE = "PRICE"
    DIRECTION = "DIRECTION"
    PERIOD = "PERIOD"
    DATE_RANGE = "DATE_RANGE"
    MARKET = "MARKET"  # 국내/미국 (서킷브레이커처럼 시장마다 답이 다른 질문)
    INVESTOR = "INVESTOR"  # 외국인/기관 등 (투자자별 순위)
    SIDE = "SIDE"  # 순매수/순매도 (투자자별 순위)
    RANK_TYPE = "RANK_TYPE"  # 거래대금/거래량/거래량 급증률 (거래 순위)
    RANK_MARKET = "RANK_MARKET"  # 국내/미국/코인 (거래 순위만 코인이 있다)
    GOAL_TYPE = "GOAL_TYPE"  # 총 자산/월간·연간 실현손익 (투자 목표 변경)
    GOAL_AMOUNT = "GOAL_AMOUNT"  # 새 목표 금액 (투자 목표 변경)


REJECT_TEXT: dict[str, str] = {
    RejectReason.ACTION: "지원하지 않는 질문입니다. 시세·수급·일정 같은 정보 조회만 할 수 있어요.",
    RejectReason.OUT_OF_SCOPE: "투자 데이터 관련 질문만 답할 수 있어요. 시세·수급·일정·내 계좌를 물어보세요.",
    RejectReason.PAPER_TRADE: "모의투자는 관리자 페이지에서 확인해 주세요.",
    RejectReason.GREETING: "네, 무엇을 조회해 드릴까요?",
    RejectReason.DATE_UNSUPPORTED: (
        "해당 데이터는 과거 날짜 조회를 지원하지 않습니다. 당일(최근) 데이터만 제공할 수 있습니다."
    ),
    RejectReason.UNSUPPORTED: "아직 지원하지 않는 기능입니다. 시세·수급·업종·일정 같은 정보를 물어보세요.",
    RejectReason.FX_PERIOD: (
        "환율은 하루 단위로만 조회할 수 있습니다. 날짜를 하나로 물어봐 주세요. (예: 어제 환율, 10월 23일 환율)"
    ),
}

ASK_TEXT: dict[str, str] = {
    Missing.STOCK: "어떤 종목인가요?",
    Missing.PRICE: "목표가를 얼마로 할까요?",
    Missing.DIRECTION: "목표가 이상일 때와 이하일 때 중 언제 알려 드릴까요?",
    Missing.PERIOD: "기간을 알려 주세요. (예: 오늘, 최근 5일, 이달)",
    Missing.DATE_RANGE: "언제부터 언제까지의 일정인가요?",
    Missing.MARKET: "국내와 미국 중 어느 시장인가요?",
    Missing.INVESTOR: "외국인과 기관 중 어느 쪽인가요? (연기금·개인도 볼 수 있어요)",
    Missing.SIDE: "순매수와 순매도 중 어느 쪽인가요?",
    Missing.RANK_TYPE: "거래대금, 거래량, 거래량 급증률 중 어떤 순위인가요?",
    Missing.RANK_MARKET: "국내, 미국, 코인 중 어느 시장인가요?",
    Missing.GOAL_TYPE: "총 자산, 월간 실현손익, 연간 실현손익 중 어떤 목표인가요?",
    Missing.GOAL_AMOUNT: "목표 금액을 얼마로 할까요?",
}

CHOOSE_STOCK = "어떤 종목인가요? 아래에서 골라 주세요."
CONFIRM_STOCK = "정확히 일치하는 종목이 없습니다. 아래 종목이 맞나요?"
CONFIRM_ALERT = "아래 내용으로 알림을 등록할까요?"
CONFIRM_ALERT_DELETE = "아래 알림을 삭제할까요?"
CONFIRM_GOAL = "아래 내용으로 투자 목표를 변경할까요?"
ALL_FAILED = "조회하지 못했습니다. 카드의 오류 내용을 확인해 주세요."
PICK_EXPIRED = "선택할 항목이 만료되었습니다. 다시 질문해 주세요."
AUTH_REQUIRED = "2차 비밀번호 인증이 필요한 질문입니다."
RESUME_EXPIRED = "대기 중인 질문이 만료되었습니다. 다시 질문해 주세요."
LLM_ERROR = "AI 기능이 일시 중단되었습니다. 잠시 후 다시 시도해 주세요."
TIMEOUT = "응답 시간이 초과되어 일부 결과만 표시합니다."
RATE_LIMIT = "질문이 너무 잦습니다. 1분 뒤 다시 시도해 주세요."
COST_LIMIT = "이번 달 AI 사용 한도에 도달했습니다. 다음 달에 다시 이용해 주세요."


# 조회 성공 답변은 화면에서 카드만 보이고 이 문구는 목록·검색용으로 저장만 된다. 기준 시각은 카드에 있다
DONE = "조회 결과입니다"
