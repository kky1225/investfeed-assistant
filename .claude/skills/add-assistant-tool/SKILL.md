---
name: add-assistant-tool
description: InvestFeed AI 비서에 새 도구(get_*, show_*, create_* 등)를 추가하거나 기존 도구의 인자를 바꿀 때 사용. Kotlin /internal/assistant/tools 엔드포인트, Python registry, 프론트 카드를 세 저장소에 걸쳐 짝으로 맞추는 순서를 따른다.
argument-hint: "<도구 이름> <무엇을 조회하는지>"
---

# 비서 도구 추가

대상: $ARGUMENTS

도구 하나가 세 저장소에 걸친다 (경로는 IdeaProjects 기준).
- backend: investfeed-backend/src/main/kotlin/com/example/investfeed/internal/assistant/
- assistant: investfeed-assistant/app/
- frontend: investfeed-frontend/src/components/assistant/cards/

## 시작 전
- 종류를 정한다: DATA(공개 데이터, 결과 전체 반환) / DISPLAY(개인 데이터, 카드 참조 ID 만 — C-01) / ACTION(설정 변경, preview 후 실행은 프론트)
- 같은 종류의 기존 도구 하나를 세 저장소 끝까지 따라 읽고 그대로 맞춘다. DATA 는 get_exchange_rates, DISPLAY 는 show_my_holding, ACTION 은 create_price_alert
- 이름은 snake_case 동사형. DISPLAY 는 반드시 show_ 로 시작한다 (ServiceTokenFilter 가 이 접두사로 2차 인증을 강제한다)
- investfeed-backend/docs/assistant-mvp-scope.md 범위 밖이면 구현하지 말고 사용자에게 먼저 알린다

## 1. Kotlin (investfeed-backend)
1. dto/req/XxxReq.kt — 필드 이름을 Python input_schema 속성 이름과 똑같이(camelCase). GET 쿼리스트링으로 들어와 @ModelAttribute 로 묶인다. 선택 인자는 nullable, 기본값 null
2. tool/ — 관련 XxxToolService 에 메서드를 추가하거나 새로 만든다. 사용자에게 보일 실패는 ToolException(메시지), 날짜는 AssistantDate.parse(req.date)?.resolve(시장)
3. InternalToolController — @GetMapping("도구이름") + tool("도구이름", "출처 문구") { ... } 래퍼
4. domain/assistant/enum/ChatLogLabel.kt — TOOL 맵에 관리자 화면 문구 한 줄

## 2. Python (investfeed-assistant)
1. app/tools/registry.py _SPECS 에 ToolSpec — description 에 무엇을 돌려주는지 + 예시 발화 3~6개. 기존 도구와 헷갈릴 수 있으면 양쪽 description 에 "X만 물으면 Y" 를 넣는다
2. 같은 파일 모듈 docstring 의 "이후 추가:" 에 "도구이름 YYYY-MM-DD" 를 덧붙인다
3. strict 예산 — strict 도구의 선택 인자 합계는 STRICT_OPTIONAL_LIMIT(24) 이하. 넘으면 import 시 RuntimeError.
   현재 합계: `uv run python -c "from app.tools.registry import _SPECS; print(sum(t.optional_count() for t in _SPECS if t.strict))"`
   한도에 걸리면 새 도구를 strict=False 로 둘지 사용자와 상의한다
4. date 인자를 받으면 app/chat/date_context.py 의 DATED_TOOLS 에 추가
5. description 만으로 도구 선택이 갈리지 않을 때만 app/chat/prompts.py SYSTEM_PROMPT "도구 고르는 법" 에 한 줄
- core_client.py 는 고치지 않는다 (registry 의 path 로 자동 호출)

## 3. 프론트 (investfeed-frontend)
1. TurnCardView.tsx — CARD_LABEL 에 이름
2. TurnCardView.tsx switch 에 case — 결과가 DataToolService.MarketCard 면 MarketBriefCard 를 재사용한다.
   새 형태면 MarketCards.tsx(DATA)·PersonalCards.tsx(DISPLAY) 에 카드, src/type/AssistantType.ts 에 payload 타입 (Kotlin 반환 클래스와 필드·nullable 을 맞춘다)

## 완료 기준
- backend: ./gradlew testClasses 통과 (Stop hook 이 실행)
- assistant: uv run pytest, uv run ruff check 통과 (registry import 때 strict 예산 검사도 같이 돈다)
- frontend: npx tsc --noEmit -p tsconfig.app.json 통과
- 실제 질문 → 카드 확인은 서버를 띄워야 하므로 사용자가 직접 한다

## 출력
- 저장소별 변경 파일 목록
- 추가한 도구 요약: 이름 · 종류 · 인자(필수/선택) · Kotlin 경로
- 사용자가 직접 확인할 질문 예시 2~3개
