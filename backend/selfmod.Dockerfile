# Local, explicitly-built runner for Layer 3A Part 2D. The application never
# pulls or builds this image automatically. package-lock.json and pinned Python
# requirements make tool installation an operator-reviewed build-time step;
# proposal execution itself always runs with Docker networking disabled.
FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
COPY backend/requirements.txt /opt/echo/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /opt/echo/requirements.txt

COPY frontend/package.json frontend/package-lock.json /opt/frontend/
RUN cd /opt/frontend && npm ci --no-audit --no-fund

COPY backend/selfmod_runner.py /opt/echo/selfmod_runner.py
RUN useradd --create-home --uid 10001 sandbox \
    && mkdir -p /tmp/home \
    && chown -R sandbox:sandbox /tmp/home

USER sandbox
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin"
ENTRYPOINT ["/opt/venv/bin/python", "/opt/echo/selfmod_runner.py"]
