# Vibecoding Agent Runtime Image
# Architecture §7 / §9.1 / §13
#
# Contains: Python 3.12, Node.js 20, npm, Git, Nginx
# Does NOT contain: platform backend source, application-specific frameworks,
#                   API keys, database credentials
#
# Project dependencies (React, Vite, etc.) are installed into /workspace
# at runtime by build_tools.py — not baked into this image.

FROM python:3.12-slim AS base

# Install Node.js 20, npm, git, nginx, curl, Java JDK, Maven, and build tools for any tech stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    nginx \
    gnupg \
    build-essential \
    procps \
    default-jdk-headless \
    maven \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify installs
RUN node --version && npm --version && git --version && nginx -v && java -version && mvn -version

# Create non-root agent user (§9.1: run as non-root)
RUN groupadd -r agent && useradd -r -g agent -m -d /home/agent agent

# App directory
WORKDIR /app

# Upgrade pip and install Playwright first for persistent Docker caching
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir playwright sourcemap langgraph langchain-core \
    && playwright install chromium --with-deps

# Copy pyproject.toml and source code
COPY pyproject.toml ./
COPY agent/ ./agent/
COPY mcp/ ./mcp/
COPY runtime/ ./runtime/
COPY infrastructure/ ./infrastructure/
COPY policies/ ./policies/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Install package in editable mode
RUN pip install --no-cache-dir -e .

# Copy Nginx config
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Create workspace directory — bind-mounted at runtime
RUN mkdir -p /workspace && chown agent:agent /workspace

# Make scripts executable
RUN sed -i 's/\r$//' scripts/*.sh && chmod +x scripts/entrypoint.sh scripts/healthcheck.sh

# Nginx log directory permissions
RUN chown -R agent:agent /var/log/nginx /var/lib/nginx /var/run 2>/dev/null || true

# Switch to non-root user
# Note: nginx needs to start as root on port 80, then we drop privileges
# For strict non-root: change nginx to listen on >1024 and run as agent from the start

# Environment defaults (overridden at container start by AgentManager)
ENV WORKSPACE_PATH=/workspace
ENV MODEL_NAME=claude-sonnet-4-5
ENV MODEL_PROVIDER=anthropic
ENV PREVIEW_PORT=80
ENV APP_PORT=3000
ENV TOOL_USE_ENABLED=true
ENV WEB_SEARCH_ENABLED=true
ENV RESEARCH_TOOLS_ENABLED=false
ENV MAX_TOOL_CALLS=50
ENV PYTHONUNBUFFERED=1
ENV NODE_PATH=/workspace/node_modules

# Expose port 80 for preview (Nginx) and 8080 for optional agent API
EXPOSE 80

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD /app/scripts/healthcheck.sh

# Entrypoint
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
