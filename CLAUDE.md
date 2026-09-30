# investfeed-assistant

InvestFeed AI 투자 비서의 Python 서비스. 설계 문서는 `../investfeed-backend/docs/assistant-*.md` 를 따른다.

## 규칙
- LangChain 을 설치·사용하지 않는다. 그래프는 LangGraph, 모델 호출은 공식 `anthropic` SDK 직접
- 개인 데이터(보유·잔고·수익률)는 그래프 state·체크포인트·로그·프롬프트에 넣지 않는다 (C-01). 표시 도구는 Kotlin 카드 참조 ID 만 다룬다
- 사용자 JWT 는 받지 않는다. 비서 토큰(RS256, JWKS) 만 검증하고 Kotlin `/internal` 에는 같은 토큰을 전파한다
- 브리핑·알림·타임라인은 Kotlin 소유. 이 서비스는 질문 턴만 만들고 결과를 Kotlin 타임라인에 append 한다
- 모의투자 데이터는 다루지 않는다 (관리자 전용, C-12)
- 의존성은 `uv add` 로만 추가하고 `uv.lock` 을 커밋한다. 업그레이드는 `uv lock --upgrade` 후 테스트 통과 시만

## 명령
- 실행: `uv run assistant   # = uvicorn app.main:app, host/port 는 .env (HOST, PORT), --reload`
- 린트: `uv run ruff check`
