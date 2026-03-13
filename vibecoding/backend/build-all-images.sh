#!/bin/bash
set -e

echo "Building all VibeCoding executor images..."
echo ""

echo "[1/9] Building Python executor..."
docker build -t vibecoding-python-executor:latest -f Dockerfile.python-executor .

echo ""
echo "[2/9] Building Node.js executor..."
docker build -t vibecoding-nodejs-executor:latest -f Dockerfile.nodejs-executor .

echo ""
echo "[3/9] Building Java executor..."
docker build -t vibecoding-java-executor:latest -f Dockerfile.java-executor .

echo ""
echo "[4/9] Building Go executor..."
docker build -t vibecoding-go-executor:latest -f Dockerfile.go-executor .

echo ""
echo "[5/9] Building C executor..."
docker build -t vibecoding-c-executor:latest -f Dockerfile.c-executor .

echo ""
echo "[6/9] Building C++ executor..."
docker build -t vibecoding-cpp-executor:latest -f Dockerfile.cpp-executor .

echo ""
echo "[7/9] Building Rust executor..."
docker build -t vibecoding-rust-executor:latest -f Dockerfile.rust-executor .

echo ""
echo "[8/9] Building PHP executor..."
docker build -t vibecoding-php-executor:latest -f Dockerfile.php-executor .

echo ""
echo "[9/9] Building Ruby executor..."
docker build -t vibecoding-ruby-executor:latest -f Dockerfile.ruby-executor .

echo ""
echo "========================================"
echo "All images built successfully!"
echo "========================================"
echo ""
echo "Available images:"
docker images | grep vibecoding
