# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# Minimal dependency builder for the production runtime.
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY app ./app

RUN python -m pip install --upgrade pip \
    && python -m pip install --prefix=/install .

# Reproducible test/static-analysis target. Development tools remain isolated
# from the runtime stage.
FROM python:${PYTHON_VERSION}-slim AS test

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

# Reuse the already-built production dependency set so the test image does
# not compile dlib a second time. Only development tooling is added here.
COPY --from=builder /install /usr/local

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        "pytest>=9.0.3,<10.0" \
        "pytest-asyncio>=1.4,<2.0" \
        "httpx>=0.27,<1.0" \
        "ruff>=0.7,<1.0" \
        "mypy>=1.13,<2.0" \
        "types-openpyxl>=3.1,<4.0"

CMD ["sh", "-lc", "alembic upgrade head && pytest"]

# Minimal production runtime.
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="shikshasathi-backend-v2" \
      org.opencontainers.image.description="ShikshaSathi FastAPI deployable MVP backend"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /usr/sbin/nologin appuser \
    && install -d -o appuser -g appuser /app /var/lib/shikshasathi/biometric

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini ./alembic.ini
COPY --chown=appuser:appuser scripts ./scripts

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)" || exit 1

STOPSIGNAL SIGTERM

# One worker is deliberate: the shipped login limiter is process-local. Scale
# horizontally only with a shared limiter introduced at the trusted ingress.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
