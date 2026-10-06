"""고정 응답 문구. LLM 은 문장을 쓰지 않는다 (A안) — 사용자에게 보이는 문장은 전부 여기서 나온다."""

from enum import StrEnum


class RejectReason(StrEnum):
    ACTION = "ACTION"  # 매매·행동·판단·예측 ("사도 돼", "사줘", "오를까")
    OUT_OF_SCOPE = "OUT_OF_SCOPE"  # 투자 데이터와 무관, 설명·요약 요청
    PAPER_TRADE = "PAPER_TRADE"  # 모의투자·자동매매 (관리자 전용, C-12)
    GREETING = "GREETING"  # 인사


class Missing(StrEnum):
    STOCK = "STOCK"
    PRICE = "PRICE"
    DIRECTION = "DIRECTION"
    PERIOD = "PERIOD"
    DATE_RANGE = "DATE_RANGE"


REJECT_TEXT: dict[str, str] = {
    RejectReason.ACTION: "지원하지 않는 질문입니다. 시세·수급·일정 같은 정보 조회만 할 수 있어요.",
    RejectReason.OUT_OF_SCOPE: "투자 데이터 관련 질문만 답할 수 있어요. 시세·수급·일정·내 계좌를 물어보세요.",
    RejectReason.PAPER_TRADE: "모의투자는 관리자 페이지에서 확인해 주세요.",
    RejectReason.GREETING: "네, 무엇을 조회해 드릴까요?",
}

ASK_TEXT: dict[str, str] = {
    Missing.STOCK: "어떤 종목인가요?",
    Missing.PRICE: "목표가를 얼마로 할까요?",
    Missing.DIRECTION: "목표가 이상일 때와 이하일 때 중 언제 알려 드릴까요?",
    Missing.PERIOD: "기간을 알려 주세요. (예: 오늘, 최근 5일, 이달)",
    Missing.DATE_RANGE: "언제부터 언제까지의 일정인가요?",
}

CHOOSE_STOCK = "어떤 종목인가요? 아래에서 골라 주세요."
CONFIRM_ALERT = "아래 내용으로 알림을 등록할까요?"
ALL_FAILED = "조회하지 못했습니다. 카드의 오류 내용을 확인해 주세요."
PICK_EXPIRED = "선택할 항목이 만료되었습니다. 다시 질문해 주세요."
LLM_ERROR = "AI 기능이 일시 중단되었습니다. 잠시 후 다시 시도해 주세요."
TIMEOUT = "응답 시간이 초과되어 일부 결과만 표시합니다."
RATE_LIMIT = "질문이 너무 잦습니다. 1분 뒤 다시 시도해 주세요."
COST_LIMIT = "이번 달 AI 사용 한도에 도달했습니다. 다음 달에 다시 이용해 주세요."


# 조회 성공 답변은 화면에서 카드만 보이고 이 문구는 목록·검색용으로 저장만 된다. 기준 시각은 카드에 있다
DONE = "조회 결과입니다"
