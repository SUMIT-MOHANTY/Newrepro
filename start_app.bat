@echo off
echo Starting Backend...
start cmd /k "cd backend && call venv\Scripts\activate && uvicorn main:app --reload --port 8000"

echo Starting Frontend...
start cmd /k "cd frontend && npm run dev"

echo Servers are running in separate windows. Close those windows to stop the servers.
