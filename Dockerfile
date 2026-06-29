FROM python:3.12-slim AS backend

WORKDIR /app

# Install uv from PyPI rather than `COPY --from=ghcr.io/astral-sh/uv:latest`
# — ghcr.io is unreachable from many networks (China, restricted VPC) and
# turns a single image pull into a build-breaking failure. PyPI is mirrored
# everywhere and Docker Hub already gave us python:3.12-slim.
RUN pip install --no-cache-dir uv

# Stage 1: dependency layer (cacheable; only invalidated by lockfile change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# System libs Playwright Chromium needs + the browser binary itself.
# Skipping these means the Comparison screenshot button + daily push
# job will fail with "Executable doesn't exist at ...".
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libglib2.0-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libx11-6 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        wget \
        xdg-utils \
    && rm -rf /var/lib/apt/lists/* \
    && uv run playwright install chromium

# Stage 2: install the project itself. This is what makes `stake_watch.main`
# importable inside the container; running `uv sync` before src/ existed
# only installed the dependency tree, never the package.
COPY src/ src/
COPY config/ config/
RUN uv sync --frozen --no-dev

ENV DATABASE_URL=sqlite:////data/stake_watch.db

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "python", "-m", "stake_watch.main"]
