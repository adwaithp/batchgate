# The BatchGate backend. One image, two services in docker-compose.yml:
#   api     sh start.sh                         (migrations + demo data if empty, then uvicorn)
#   worker  arq app.worker.WorkerSettings       (Claude reads uploaded COAs here)

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

RUN mkdir -p /data/uploads
EXPOSE 8000
CMD ["sh", "start.sh"]
