"""프로젝트 진입점. `uv run assistant` 또는 `uv run python -m app`. host/port 는 .env(HOST, PORT)에서 읽는다."""

import uvicorn

from app.config import get_settings


def main() -> None:
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=True)


if __name__ == "__main__":
    main()
