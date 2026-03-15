@echo off
echo ========================================
echo Rebuilding Universal Agent Runtime
echo ========================================
echo.

echo Current Features:
echo - Self-healing AI diagnostics
echo - Dynamic runtime bootstrapping
echo - Multi-stack compatibility
echo - Better error logging
echo.

echo Step 1: Removing old image...
docker rmi vibecoding-agent-runtime:latest 2>nul

echo.
echo Step 2: Building Universal Runtime image...
docker build --no-cache -f vibecoding\backend\docker\agent-runtime.Dockerfile -t vibecoding-agent-runtime:latest vibecoding\backend\docker

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Agent Runtime now supports:
    echo - Automatic dependency installation
    echo - AI-driven error remediation
    echo - Unified control supervisor
    echo - Improved preview reliability
    echo.
    echo Next steps:
    echo 1. Restart Backend: cd vibecoding\backend ^&^& python main.py
    echo 2. Restart Frontend: cd vibecoding\frontend ^&^& npm run dev
    echo 3. Start a new chat to test the agent!
    echo.
) else (
    echo.
    echo BUILD FAILED
    echo.
    pause
    exit /b 1
)
