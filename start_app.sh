#!/bin/bash

# Function to kill processes on exit
cleanup() {
    echo "Stopping servers..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

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
