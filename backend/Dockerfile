FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /app/data/chroma

# ECHO Layer 0 — run as a non-root user. The /app/data volume mount (see
# docker-compose.yml) needs to stay writable by this user, hence chown-ing
# it here rather than leaving it root-owned.
RUN useradd --create-home --uid 1000 echo && chown -R echo:echo /app
USER echo

EXPOSE 8000

# ECHO Layer 0 — matches GET /api/health (see app/main.py), which does no
# heavy checks (no DB/network calls) so this stays fast and doesn't report
# unhealthy just because a downstream dependency (Ollama, a cloud provider)
# is temporarily unavailable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
