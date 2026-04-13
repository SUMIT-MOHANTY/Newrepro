# Universal agent runtime - Dynamic Bootstrapper 🚀
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

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
    rsync \
    tree \
    psmisc \
    procps \
    net-tools \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Pre-install essential tooling for all major frameworks
# - serve: Static file server for React/Vue/Angular/Svelte production builds
# - concurrently: For running multiple processes (frontend+backend)
RUN npm install -g serve@latest concurrently@latest 2>/dev/null || npm install -g serve concurrently

WORKDIR /project

# Copy the "Intelligence" (Supervisor, AI Agent, Codegen, and Vibe Fixer)
COPY supervisor.py /usr/local/bin/supervisor.py
COPY ai-agent.py /usr/local/bin/ai-agent.py
COPY codegen.py /usr/local/bin/codegen.py
COPY vibe-fix-all.py /usr/local/bin/vibe-fix-all.py

# Fix line endings (Windows CRLF → Unix LF) and make executable
RUN sed -i 's/\r$//' /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/codegen.py /usr/local/bin/vibe-fix-all.py && \
    chmod +x /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/codegen.py /usr/local/bin/vibe-fix-all.py

# Install absolute essentials for the Agent's own AI communication + common Python web frameworks
RUN pip3 install --no-cache-dir --default-timeout=1000 --retries 10 \
    requests flask fastapi uvicorn gunicorn

# Start NGINX by default
EXPOSE 80

# Agent is the single entrypoint — it manages Nginx, codegen, and deployment internally
ENTRYPOINT ["python3", "/usr/local/bin/ai-agent.py"]