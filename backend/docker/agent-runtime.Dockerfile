# Universal agent runtime with Python and Node.js pre-installed
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Use reliable Ubuntu mirrors and install Python, Node.js, and essentials
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirror.kakao.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirror.kakao.com/ubuntu/|g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        wget \
        ca-certificates \
        git \
        build-essential \
        python3 \
        python3-pip \
        python3-venv \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy supervisor and AI agent scripts
COPY supervisor.py /usr/local/bin/supervisor.py
COPY ai-agent.py /usr/local/bin/ai-agent.py
COPY agent-entrypoint-selfheal.sh /usr/local/bin/agent-entrypoint.sh

# Fix line endings (Windows CRLF to Unix LF)
RUN sed -i 's/\r$//' /usr/local/bin/supervisor.py && \
    sed -i 's/\r$//' /usr/local/bin/ai-agent.py && \
    sed -i 's/\r$//' /usr/local/bin/agent-entrypoint.sh

# Make executable
RUN chmod +x /usr/local/bin/supervisor.py /usr/local/bin/ai-agent.py /usr/local/bin/agent-entrypoint.sh

# Install requests for AI agent
RUN pip3 install requests

# Health check - try common ports
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:5000/ || curl -f http://localhost:3000/ || exit 1

# Use supervisor as entrypoint (it manages version switching)
ENTRYPOINT ["/usr/local/bin/supervisor.py"]
