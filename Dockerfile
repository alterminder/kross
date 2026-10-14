# One image: the API, the built frontend, the shipped content and the migrations.
# Build tools stay out of the runtime stage: no uv, no pip, no compilers.

# Stage 1: frontend build. Node runs here only.
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: python environment build with uv.
FROM python:3.12-alpine3.24 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev

# Stage 3: runtime. Refreshed base packages, venv only, non-root UID 10001.
# Alpine leaves out unused Debian packages with outstanding advisories and
# keeps one musl libc across builder and runtime.
FROM python:3.12-alpine3.24
RUN apk update && apk upgrade --no-cache \
    && if python -m pip --version >/dev/null 2>&1; then python -m pip uninstall -y pip setuptools wheel; fi
ENV UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NLAB_PRODUCTION=true \
    PATH="/app/.venv/bin:$PATH" \
    NLAB_CONTENT_DIR=/app/content \
    NLAB_STATIC_DIR=/app/static
WORKDIR /app/backend
COPY --from=builder /app/.venv /app/.venv
COPY backend/ ./
COPY content/ /app/content/
COPY --from=frontend /frontend/dist /app/static
RUN adduser -S -D -H -u 10001 nlab && chown -R nlab /app
USER nlab
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
# The app listens on the container interface; compose publishes it on host
# loopback only. Uvicorn's access log is disabled (it records query strings,
# e.g. OAuth callbacks); use the proxy's redacted nlab_safe log instead.
# NLAB_PRODUCTION is forced on in the image (offline tools like
# nlab.api.openapi set production=False explicitly): example or manual
# deployments cannot silently bypass the production gates in Settings.
# --limit-concurrency/--timeout-keep-alive bound connection abuse.
# NLAB_FORWARDED_ALLOW_IPS must be the proxy->app peer, never '*'
# (docs/deployment.md). Sub-path hosting is not supported.
CMD ["sh", "-c", "\
  if [ -n \"${NLAB_ROOT_PATH:-}\" ]; then \
    echo 'NLAB_ROOT_PATH is set but this kit only supports root-path hosting (leave it empty)' >&2; exit 1; \
  fi; \
  exec uvicorn nlab.api.main:app --host 0.0.0.0 --port 8000 \
    --no-access-log --proxy-headers \
    --limit-concurrency 32 --timeout-keep-alive 5 \
    --forwarded-allow-ips=\"${NLAB_FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
