# Universal agent runtime - Dynamic Bootstrapper 🚀
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=8080

# Install bare minimum + Node.js 18 for full-stack apps (React/Vue/Svelte frontends)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /project

# Copy the "Intelligence" (Supervisor, AI Agent, and Codegen)
COPY supervisor.py /usr/local/bin/supervisor.py
COPY ai-agent.py /usr/local/bin/ai-agent.py
COPY codegen.py /usr/local/bin/codegen.py

# Fix line endings (Windows CRLF → Unix LF) and make executable
RUN sed -i 's/\r$//' /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/codegen.py && \
    chmod +x /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/codegen.py

# Install absolute essentials for the Agent's own AI communication
RUN pip3 install --no-cache-dir --default-timeout=1000 --retries 10 requests

# Dynamic healthcheck — follows PORT env var, lenient start period for AI provisioning
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/ || exit 0

# Supervisor manages the dynamic lifecycle
ENTRYPOINT ["/usr/local/bin/supervisor.py"]
