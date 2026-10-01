#!/bin/bash
# Agent Runtime entrypoint script
# Architecture §7 scripts/entrypoint.sh
# Starts Nginx in background, runs the agent, and keeps preview servers alive.

set -e

echo "[Entrypoint] Starting Vibecoding Agent Runtime"
echo "[Entrypoint] Session: ${SESSION_ID:-unknown}"
echo "[Entrypoint] Workspace: ${WORKSPACE_PATH:-/workspace}"

# Ensure workspace directory exists
mkdir -p "${WORKSPACE_PATH:-/workspace}"

# Start Nginx in background (serves fullstack preview on port 80)
echo "[Entrypoint] Starting Nginx on port 80..."
# Fix Nginx permissions for non-root user
mkdir -p /var/run /var/log/nginx /var/lib/nginx/tmp
chown -R agent:agent /var/run /var/log/nginx /var/lib/nginx 2>/dev/null || true
# Use port 8080 instead of 80 if not root
if [ "$(id -u)" != "0" ]; then
    sed -i 's/listen 80;/listen 8080;/g' /etc/nginx/conf.d/*.conf 2>/dev/null || true
    sed -i 's/listen       80;/listen       8080;/g' /etc/nginx/nginx.conf 2>/dev/null || true
fi
nginx -g 'daemon off; pid /tmp/nginx.pid;' &
NGINX_PID=$!
echo "[Entrypoint] Nginx started (PID: $NGINX_PID)"

# Setup signal trapping for graceful container shutdown
cleanup() {
    echo "[Entrypoint] Received termination signal. Stopping services..."
    kill -TERM "$NGINX_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Run the persistent agent runtime daemon
echo "[Entrypoint] Starting agent daemon..."
cd /app
python -u -m agent.main
AGENT_EXIT=$?

echo "[Entrypoint] Agent session finished with code: $AGENT_EXIT"
kill -TERM "$NGINX_PID" 2>/dev/null || true
exit $AGENT_EXIT
