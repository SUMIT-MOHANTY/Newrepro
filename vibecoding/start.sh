#!/bin/bash

echo "Starting Bourtec VibeCoding..."
echo ""

echo "Starting Backend..."
cd backend
source venv/bin/activate
python main.py &
BACKEND_PID=$!

cd ..

sleep 3

echo "Starting Frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Both servers are running..."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT

wait
