FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

RUN adduser --disabled-password --gecos "" appuser

COPY --chown=appuser:appuser hello.py ./

USER appuser

ENTRYPOINT ["/app/.venv/bin/hello"]
