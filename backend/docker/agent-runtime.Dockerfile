# Minimal base image - AI agent installs everything dynamically
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install ONLY essentials: curl for health checks, and basic build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        wget \
        ca-certificates \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy intelligent agent entrypoint (bash script, no Python dependency)
COPY agent-entrypoint.sh /usr/local/bin/agent-entrypoint.sh
RUN chmod +x /usr/local/bin/agent-entrypoint.sh

# Health check - try common ports
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/ || curl -f http://localhost:5000/ || curl -f http://localhost:3000/ || exit 1

ENTRYPOINT ["/usr/local/bin/agent-entrypoint.sh"]
