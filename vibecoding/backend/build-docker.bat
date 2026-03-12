# Build Docker images for code execution
echo "Building Docker images for code execution..."

# Build HTML/Nginx executor
echo "Building vibecoding-code-executor (HTML/Nginx)..."
docker build -f Dockerfile.code-executor -t vibecoding-code-executor:latest .

if %ERRORLEVEL% EQU 0 (
    echo "✅ vibecoding-code-executor built successfully!"
) else (
    echo "❌ Failed to build vibecoding-code-executor"
    exit /b 1
)

# Build Python executor
echo "Building vibecoding-python-executor (Flask/Python)..."
docker build -f Dockerfile.python-executor -t vibecoding-python-executor:latest .

if %ERRORLEVEL% EQU 0 (
    echo "✅ vibecoding-python-executor built successfully!"
) else (
    echo "❌ Failed to build vibecoding-python-executor"
    exit /b 1
)

echo.
echo "✅ All Docker images built successfully!"
echo "Available images:"
echo "  - vibecoding-code-executor:latest (for HTML/CSS/JS)"
echo "  - vibecoding-python-executor:latest (for Python/Flask)"
