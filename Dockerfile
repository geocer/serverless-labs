# ── Stage 1: builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY app/requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim

# non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# copia dependências instaladas no builder
COPY --from=builder /install /usr/local

# copia código da aplicação
COPY app/ .

# ajusta permissões
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# gunicorn: 2 workers * (2 × CPUs + 1) — ajuste GUNICORN_WORKERS pra escalar
ENV GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    PORT=8080 \
    LOG_LEVEL=INFO

CMD gunicorn app:app \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS}" \
    --threads "${GUNICORN_THREADS}" \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    --log-level "${LOG_LEVEL}"
