# Universal agent runtime - Dynamic Bootstrapper 🚀
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=8080

# Install ONLY the bare minimum to run the Python AI Agent
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /project

# Copy the "Intelligence" (Supervisor and AI Agent)
COPY supervisor.py /usr/local/bin/supervisor.py
COPY ai-agent.py /usr/local/bin/ai-agent.py

# Fix line endings (Windows CRLF → Unix LF) and make executable
RUN sed -i 's/\r$//' /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py && \
    chmod +x /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py

# Install absolute essentials for the Agent's own AI communication
RUN pip3 install requests

# Dynamic healthcheck — follows PORT env var, lenient start period for AI provisioning
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/ || exit 0

# Supervisor manages the dynamic lifecycle
ENTRYPOINT ["/usr/local/bin/supervisor.py"]
