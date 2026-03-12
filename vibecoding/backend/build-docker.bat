# Build Docker image for code execution
echo "Building Docker image for code execution..."

docker build -f Dockerfile.code-executor -t vibecoding-code-executor:latest .

if %ERRORLEVEL% EQU 0 (
    echo "✅ Docker image built successfully!"
    echo "Image name: vibecoding-code-executor:latest"
) else (
    echo "❌ Failed to build Docker image"
    exit /b 1
)
