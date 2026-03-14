#!/bin/bash
set -e

echo "🤖 VibeCoding Universal Agent Starting..."
echo "📂 Workspace: /app"

# Function to install Python if needed
install_python() {
    if command -v python3 &> /dev/null; then
        echo "✅ Python already installed ($(python3 --version))"
        return 0
    fi
    
    echo "📦 Installing Python..."
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv
    echo "✅ Python installed ($(python3 --version))"
}

# Function to install Node.js if needed
install_nodejs() {
    if command -v node &> /dev/null; then
        echo "✅ Node.js already installed ($(node --version))"
        return 0
    fi
    
    echo "📦 Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
    echo "✅ Node.js installed ($(node --version))"
}

# Detect project type
detect_project() {
    echo "🔍 Analyzing project..."
    
    # Django
    if [ -f "manage.py" ]; then
        echo "🎯 Detected: Django Project"
        return 1
    fi
    
    # Flask - check file contents
    if ls *.py &> /dev/null; then
        if grep -qi "flask" *.py 2>/dev/null; then
            echo "🎯 Detected: Flask Application"
            return 5
        fi
    fi
    
    # Node.js
    if [ -f "package.json" ]; then
        echo "🎯 Detected: Node.js Project"
        return 2
    fi
    
    # Python (generic)
    if ls *.py &> /dev/null; then
        echo "🎯 Detected: Python Application"
        return 3
    fi
    
    # Static HTML
    if ls *.html &> /dev/null; then
        echo "🎯 Detected: Static HTML"
        return 4
    fi
    
    echo "❌ Unknown project type"
    return 0
}

# Run Django project
run_django() {
    install_python
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        echo "📦 Installing Python dependencies..."
        pip3 install -q -r requirements.txt
    fi
    
    # Run migrations
    echo "🔄 Running migrations..."
    python3 manage.py migrate --noinput 2>/dev/null || echo "⚠️ Migrations skipped"
    
    # Collect static files
    python3 manage.py collectstatic --noinput 2>/dev/null || echo "⚠️ Static files skipped"
    
    # Start server on port 5000 (consistent with Flask)
    echo "🚀 Starting Django server on 0.0.0.0:5000"
    exec python3 manage.py runserver 0.0.0.0:5000
}

# Run Node.js project
run_nodejs() {
    install_nodejs
    
    # Install dependencies
    echo "📦 Installing Node.js dependencies..."
    npm install --silent
    
    # Read package.json for start script
    if [ -f "package.json" ]; then
        if grep -q '"dev"' package.json; then
            echo "🚀 Starting with: npm run dev"
            exec npm run dev
        elif grep -q '"start"' package.json; then
            echo "🚀 Starting with: npm start"
            exec npm start
        else
            # Find main file
            MAIN=$(node -p "require('./package.json').main || 'index.js'")
            echo "🚀 Starting with: node $MAIN"
            exec node "$MAIN"
        fi
    fi
}

# Run Python application
run_python() {
    install_python
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        echo "📦 Installing Python dependencies..."
        pip3 install -q -r requirements.txt
    fi
    
    # Find main file
    MAIN_FILE=""
    for file in main.py app.py run.py server.py; do
        if [ -f "$file" ]; then
            MAIN_FILE="$file"
            break
        fi
    done
    
    if [ -z "$MAIN_FILE" ]; then
        # Use first .py file
        MAIN_FILE=$(ls *.py 2>/dev/null | head -n 1)
    fi
    
    if [ -z "$MAIN_FILE" ]; then
        echo "❌ No Python entry point found"
        exit 1
    fi
    
    echo "🚀 Starting Python app: $MAIN_FILE"
    exec python3 "$MAIN_FILE"
}

# Run static HTML
run_static() {
    install_python
    
    echo "🚀 Starting HTTP server on port 8000"
    exec python3 -m http.server 8000 --bind 0.0.0.0
}

# Run Flask application
run_flask() {
    install_python
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        echo "📦 Installing Python dependencies..."
        pip3 install -q -r requirements.txt
    fi
    
    # Find main file
    MAIN_FILE=""
    for name in app.py main.py application.py run.py; do
        if [ -f "$name" ]; then
            MAIN_FILE="$name"
            break
        fi
    done
    
    if [ -z "$MAIN_FILE" ]; then
        echo "❌ No Flask entry point found"
        exit 1
    fi
    
    # Auto-fix common Flask compatibility issues
    echo "🔧 Checking for compatibility issues..."
    
    # Fix deprecated @app.before_first_request (Flask 3.0+)
    if grep -q "@app.before_first_request" "$MAIN_FILE"; then
        echo "⚠️ Fixing deprecated @app.before_first_request..."
        sed -i 's/@app.before_first_request/# @app.before_first_request (deprecated - moved to startup)/g' "$MAIN_FILE"
        
        # Add database initialization at startup instead
        if grep -q "db.create_all()" "$MAIN_FILE"; then
            # Add initialization after app creation
            sed -i '/^app = Flask/a\\nwith app.app_context():\n    db.create_all()' "$MAIN_FILE"
        fi
    fi
    
    echo "🚀 Starting Flask server: $MAIN_FILE on port 5000"
    exec python3 "$MAIN_FILE"
}

# Main execution
cd /app

# Temporarily disable exit-on-error for detection
set +e
detect_project
PROJECT_TYPE=$?
set -e

case $PROJECT_TYPE in
    1)
        run_django
        ;;
    2)
        run_nodejs
        ;;
    3)
        run_python
        ;;
    4)
        run_static
        ;;
    5)
        run_flask
        ;;
    *)
        echo "❌ Cannot determine how to run this project"
        echo "📋 Files in workspace:"
        ls -la
        exit 1
        ;;
esac
