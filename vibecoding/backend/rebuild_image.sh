#!/bin/bash
# Script to rebuild the Docker image with updated supervisor

echo "🔨 Rebuilding vibecoding-agent-runtime image..."

cd "$(dirname "$0")/docker"

docker build -f agent-runtime.Dockerfile -t vibecoding-agent-runtime:latest .

if [ $? -eq 0 ]; then
    echo "✅ Image rebuilt successfully!"
    echo ""
    echo "⚠️  Note: Existing containers are still running the old image."
    echo "To use the new image, you need to:"
    echo "1. Stop old containers: docker stop \$(docker ps -q --filter name=vibecoding_)"
    echo "2. Remove old containers: docker rm \$(docker ps -aq --filter name=vibecoding_)"
    echo "3. The next code generation will create a new container with the updated image"
else
    echo "❌ Image build failed!"
    exit 1
fi
