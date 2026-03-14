@echo off
echo ========================================
echo Rebuilding with Django Auto-Setup
echo ========================================
echo.

echo New Features:
echo - Auto-runs Django migrations
echo - Creates static directory
echo - Collects static files
echo - Better error logging
echo.

echo Step 1: Removing old image...
docker rmi vibecoding-agent-runtime:latest 2>nul

echo.
echo Step 2: Building with Django fixes...
docker build --no-cache -f vibecoding\backend\docker\agent-runtime.Dockerfile -t vibecoding-agent-runtime:latest vibecoding\backend\docker

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Django apps will now:
    echo - Run migrations automatically
    echo - Create missing directories
    echo - Collect static files
    echo - Work properly in preview
    echo.
    echo Next steps:
    echo 1. Restart backend: cd vibecoding\backend ^&^& python main.py
    echo 2. Restart frontend: cd vibecoding\frontend ^&^& npm run dev
    echo 3. Test Django app - preview should work now!
    echo.
) else (
    echo.
    echo BUILD FAILED
    echo.
    pause
    exit /b 1
)
