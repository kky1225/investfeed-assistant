# investfeed-assistant

InvestFeed AI 투자 비서 — Q&A 서비스 (Python 3.14 · FastAPI · LangGraph). 설계: `investfeed-backend/docs/assistant-*.md`.

1단계 범위: FastAPI 뼈대 · LangGraph 5노드 스텁 · JWKS(RS256) 검증 · Kotlin `/internal` 호출 클라이언트 · 헬스.
브리핑·타임라인은 Kotlin 이 소유한다. 이 서비스는 사용자 질문 턴만 담당한다.

## 실행

```bash
cp .env.example .env            # 값 채우기
uv sync
uv run assistant   # = uvicorn app.main:app, host/port 는 .env (HOST, PORT), --reload
```

## 린트

```bash
uv run ruff check
```

## 환경변수

| 이름 | 뜻 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API 키 (1단계 미사용) |
| `CORE_JWKS_URL` | Kotlin 비서 토큰 공개키(JWKS) 주소 |
| `CORE_INTERNAL_BASE_URL` | Kotlin `/internal/assistant/tools/*` 베이스 |
| `REDIS_URL` | LangGraph 체크포인터. Redis Stack 이 아니면 메모리 체크포인터로 대체(경고 로그) |
| `DATABASE_URL` | `assistant` 스키마 (5단계 사용량·로그) |

## 인증

`Authorization: Bearer <비서 토큰>` — Kotlin `POST /api/assistant/secure/token` 이 발급한 RS256 토큰만 받는다.
사용자 JWT(HS256 쿠키)는 절대 받지 않는다. 검증: kid → JWKS 공개키, iss=`investfeed-core`, `assistant` ∈ aud, exp.
Kotlin `/internal` 호출 시 같은 토큰을 그대로 전파한다.
