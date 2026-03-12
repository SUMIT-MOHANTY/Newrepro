@echo off
echo Starting Bourtec VibeCoding...
echo.

echo Starting Backend...
start cmd /k "cd backend && venv\Scripts\activate && python main.py"

timeout /t 3 /nobreak > nul

echo Starting Frontend...
start cmd /k "cd frontend && npm run dev"

echo.
echo Both servers are starting...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
pause
