#!/bin/bash
set -e

# Agent runtime healthcheck
# Check if nginx or python agent daemon is running
pgrep -f "nginx" > /dev/null 2>&1 || pgrep -f "python" > /dev/null 2>&1 || exit 1
exit 0
