#!/bin/bash

# Function to clear specific ports
clear_ports() {
    for port in 8000 5173; do
        PID=$(lsof -t -i :$port)
        if [ ! -z "$PID" ]; then
            echo "Found process $PID on port $port, killing it..."
            kill -9 $PID 2>/dev/null
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
source venv/bin/activate
uvicorn main:app --reload --port 8000 &
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
