# Universal agent runtime - Dynamic Bootstrapper 🚀
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Install bare minimum + Node.js 18 for full-stack apps (React/Vue/Svelte frontends) + Nginx for reverse proxy
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    gnupg \
    nginx \
    lsof \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Pre-install essential tooling for all major frameworks
# - serve: Static file server for React/Vue/Angular/Svelte production builds
# - concurrently: For running multiple processes (frontend+backend)
RUN npm install -g serve@latest concurrently@latest 2>/dev/null || npm install -g serve concurrently

WORKDIR /project

# Copy the "Intelligence" (Supervisor, AI Agent, Codegen, and Health Server)
COPY supervisor.py /usr/local/bin/supervisor.py
COPY ai-agent.py /usr/local/bin/ai-agent.py
COPY codegen.py /usr/local/bin/codegen.py
COPY health_server.py /usr/local/bin/health_server.py

# Fix line endings (Windows CRLF → Unix LF) and make executable
RUN sed -i 's/\r$//' /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/codegen.py /usr/local/bin/health_server.py && \
    chmod +x /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/codegen.py /usr/local/bin/health_server.py

# Install absolute essentials for the Agent's own AI communication + common Python web frameworks
RUN pip3 install --no-cache-dir --default-timeout=1000 --retries 10 \
    requests flask fastapi uvicorn gunicorn

# Dynamic healthcheck — uses health server on port 9090
# Uses exit 1 so Docker actually marks the container unhealthy on failure
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:9090/health || exit 1

# Supervisor manages the dynamic lifecycle
ENTRYPOINT ["/usr/local/bin/supervisor.py"]

