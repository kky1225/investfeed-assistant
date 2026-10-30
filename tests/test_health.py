from fastapi.testclient import TestClient

from app.main import app


def test_health():
    # with 블록 없이 쓰면 lifespan(Redis·JWKS·Anthropic 클라이언트 생성)이 실행되지 않는다
    res = TestClient(app).get("/assistant/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
