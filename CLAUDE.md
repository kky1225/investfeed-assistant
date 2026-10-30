# investfeed-assistant

InvestFeed AI 투자 비서의 Python 서비스 (Python 3.14 · FastAPI · LangGraph). 설계 문서는 `../investfeed-backend/docs/assistant-*.md` 를 따른다.
제약 번호(C-xx)의 정의는 `../investfeed-backend/docs/assistant-requirements.md` 의 제약 절에 있다.

## 규칙
- LangChain 을 설치·사용하지 않는다. 그래프는 LangGraph, 모델 호출은 공식 `anthropic` SDK 직접
- 개인 데이터(보유·잔고·수익률)는 그래프 state·세션·로그·프롬프트에 넣지 않는다 (C-01). 표시 도구는 Kotlin 카드 참조 ID 만 다룬다
- 사용자 JWT 는 받지 않는다. 비서 토큰(RS256, JWKS) 만 검증하고 Kotlin `/internal` 에는 같은 토큰을 전파한다
- 브리핑·알림·타임라인은 Kotlin 소유. 이 서비스는 질문 턴만 만들고 결과를 Kotlin 타임라인에 append 한다
- 모의투자 데이터는 다루지 않는다 (관리자 전용, C-12)
- 의존성은 `uv add` 로만 추가하고 `uv.lock` 을 커밋한다. 업그레이드는 `uv lock --upgrade` 후 테스트 통과 시만

## 구조 (app/)
- main.py: FastAPI 앱, lifespan 에서 의존성(Redis·CoreClient·Anthropic·JWKS 검증기) 생성
- auth/: 비서 토큰 검증 (jwks.py), FastAPI 의존성 (deps.py)
- graph/: LangGraph 조립(build.py)·노드·state. 체크포인터 없음
- chat/: 턴 실행, 질문 해석, 세션(Redis), 호출 상한(guard), 프롬프트
- tools/: 도구 레지스트리(registry.py) · Kotlin `/internal/assistant/tools/*` 클라이언트(core_client.py)
- 도구를 추가할 때는 Kotlin `InternalToolController` 의 엔드포인트와 쌍으로 맞춘다

## 명령
- 실행: `uv run assistant   # = uvicorn app.main:app, host/port 는 .env (HOST, PORT), --reload` (사용자 확인 후)
- 테스트: `uv run pytest`
- 린트: `uv run ruff check` (line-length 120)
- 파일을 수정하면 hook 이 그 파일만 ruff 로 검사하고, 작업 종료 시 Stop hook 이 pytest 를 실행

## 테스트
- tests/ 에 둔다. Redis·Kotlin·Anthropic API 를 실제로 호출하지 않는다 (fetcher·클라이언트를 가짜로 주입)
- FastAPI 엔드포인트는 `TestClient(app)` 를 with 블록 없이 써서 lifespan 을 건너뛴다

## 코드 스타일
- 함수 인자·반환값에 타입 힌트를 단다
- 모듈 docstring 에 역할과 근거(명세 절·결정 날짜·C-xx)를 적는 기존 방식 유지
- 요청/응답 모델은 pydantic, 설정은 app/config.py 의 Settings 로만 읽는다

## Git
- git/gh 명령은 hook으로 차단되어 있음. 커밋·브랜치·push는 사용자가 직접 수행
- 작업이 끝나면 변경 파일 목록과 커밋 메시지 초안을 제시할 것

## 필수 규칙
- 소스 파일은 Edit/Write 도구로만 수정할 것. sed·cp·heredoc 등 Bash로 수정하면 lint·Stop hook 검증에서 빠짐
- 기능 구현 지시가 없으면 질문에 대한 답변이나 제안만 할 것
