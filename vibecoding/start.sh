#!/bin/bash

echo "Starting Bourtec VibeCoding..."
echo ""

echo "Starting Backend on port 8001..."
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!

cd ..

sleep 3

echo "Starting Frontend on port 5174..."
cd frontend
npm run dev -- --port 5174 &
FRONTEND_PID=$!

echo ""
echo "Both servers are running..."
echo "Backend (VibeCoding API):  http://localhost:8001"
echo "Frontend (VibeCoding UI):  http://localhost:5174"
echo ""
echo "Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT

wait
