FROM python:3.14.8-slim
# uv as a static binary from the official image: no pip install uv, no extra layer
COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /bin/uv

WORKDIR /app
# compile bytecode at build time (faster startup); copy because the cache mount is on another FS and hardlinks fail
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# Manifests first: the dependency layer is rebuilt only when the lock file changes
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

COPY app ./app
# one worker on purpose: the store lives in process memory, a second worker would have its own copy
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
