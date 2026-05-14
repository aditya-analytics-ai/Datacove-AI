FROM python:3.12-slim

# ── System deps ────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user (security best practice) ────────────────────────────────────
RUN groupadd -r datacove && useradd -r -g datacove -m datacove

WORKDIR /app

# ── Dependencies (cached layer) ────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── App source ────────────────────────────────────────────────────────────────
COPY . .

# ── Runtime directories (writable by non-root user) ───────────────────────────
RUN mkdir -p /app/uploads /app/datasets /app/logs \
 && chown -R datacove:datacove /app

USER datacove

# ── Metadata ──────────────────────────────────────────────────────────────────
EXPOSE 8000
LABEL maintainer="Datacove" \
      version="6.0.0" \
      description="Datacove AI data cleaning platform"

# ── Healthcheck (Docker-native, independent of compose) ───────────────────────
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Startup ───────────────────────────────────────────────────────────────────
# Uses 2 workers by default; override with UVICORN_WORKERS env var
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2} --log-level info"]
