FROM python:3.12-slim AS backend

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY config/ config/

ENV DATABASE_URL=sqlite:///data/stake_watch.db

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "python", "-m", "stake_watch.main"]
