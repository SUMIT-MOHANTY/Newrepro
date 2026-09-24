#!/bin/bash

# Function to clear specific ports
clear_ports() {
    for port in 8000 8006 5173; do
        if command -v lsof >/dev/null 2>&1; then
            PID=$(lsof -t -i :$port 2>/dev/null)
            if [ ! -z "$PID" ]; then
                echo "Found process $PID on port $port, killing it..."
                kill -9 $PID 2>/dev/null
            fi
        fi
    done
}

# Function to kill processes on exit
cleanup() {
    echo ""
    echo "Stopping servers..."
    clear_ports
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

# Clear ports before starting
clear_ports

echo "Starting Backend..."
cd backend

# Cross-platform virtual environment activation (Linux vs Windows Git Bash)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
elif [ -f "../venv/Scripts/activate" ]; then
    source ../venv/Scripts/activate
fi

# Read port from .env if present, otherwise default to 8000
BACKEND_PORT=8000
if [ -f ".env" ]; then
    PORT_IN_ENV=$(grep -E '^PORT=' .env | cut -d '=' -f 2 | tr -d ' \r\n')
    if [ ! -z "$PORT_IN_ENV" ]; then
        BACKEND_PORT=$PORT_IN_ENV
    fi
fi

uvicorn main:app --reload --port $BACKEND_PORT &
BACKEND_PID=$!
cd ..

echo "Starting Frontend..."
cd frontend
export PATH=$PATH:/usr/local/bin
npm run dev &
FRONTEND_PID=$!
cd ..

echo "Servers running. Press Ctrl+C to stop."
wait
