#!/bin/bash
set -e

echo "🤖 VibeCoding Self-Healing Agent Starting..."
echo "📂 Workspace: $(pwd)"

# Check if we're in the right directory
if [ ! "$(ls -A .)" ]; then
    echo "⚠️ Empty directory detected, checking /project structure..."
    if [ -d "/project/versions" ]; then
        # Find the latest version or use CURRENT_VERSION env var
        if [ -n "$CURRENT_VERSION" ]; then
            cd "/project/versions/$CURRENT_VERSION"
            echo "📂 Changed to: $(pwd)"
        else
            # Find latest version
            LATEST_VERSION=$(ls -1 /project/versions | sort -V | tail -1)
            if [ -n "$LATEST_VERSION" ]; then
                cd "/project/versions/$LATEST_VERSION"
                echo "📂 Changed to: $(pwd)"
            fi
        fi
    fi
fi

# Verify we have files now
if [ ! "$(ls -A .)" ]; then
    echo "❌ No files found in workspace"
    echo "📋 Directory structure:"
    ls -la /project 2>/dev/null || echo "No /project directory"
    exit 1
fi

# Maximum retry attempts for auto-fixing
MAX_RETRIES=3
RETRY_COUNT=0

# Function to log with emoji
log_info() {
    echo "ℹ️ $1"
}

log_success() {
    echo "✅ $1"
}

log_warning() {
    echo "⚠️ $1"
}

log_error() {
    echo "❌ $1"
}

# Function to install Python if needed
install_python() {
    if command -v python3 &> /dev/null; then
        log_success "Python already installed ($(python3 --version))"
        return 0
    fi
    
    log_info "Installing Python..."
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv
    log_success "Python installed ($(python3 --version))"
}

# Function to install Node.js if needed
install_nodejs() {
    if command -v node &> /dev/null; then
        log_success "Node.js already installed ($(node --version))"
        return 0
    fi
    
    log_info "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
    log_success "Node.js installed ($(node --version))"
}

# Detect project type
detect_project() {
    log_info "Analyzing project..."
    
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
    
    log_error "Unknown project type"
    return 0
}

# Auto-fix common Python errors
auto_fix_python_errors() {
    local error_log="$1"
    local fixed=0
    
    log_info "🔧 Analyzing errors for auto-fix..."
    
    # Fix 1: Missing dependencies
    if echo "$error_log" | grep -qi "ModuleNotFoundError\|ImportError\|No module named"; then
        local missing_module=$(echo "$error_log" | grep -oP "No module named '\K[^']+" | head -1)
        if [ -n "$missing_module" ]; then
            log_warning "Missing module detected: $missing_module"
            log_info "Installing missing module..."
            pip3 install -q "$missing_module" 2>/dev/null && fixed=1
        fi
    fi
    
    # Fix 2: Deprecated Flask @app.before_first_request
    if echo "$error_log" | grep -qi "before_first_request"; then
        log_warning "Deprecated Flask syntax detected"
        for file in *.py; do
            if grep -q "@app.before_first_request" "$file"; then
                log_info "Fixing $file..."
                sed -i 's/@app\.before_first_request/# @app.before_first_request (deprecated)/g' "$file"
                if grep -q "db.create_all()" "$file"; then
                    sed -i '/^app = Flask/a\\nwith app.app_context():\n    db.create_all()' "$file"
                fi
                fixed=1
            fi
        done
    fi
    
    # Fix 3: Port already in use
    if echo "$error_log" | grep -qi "Address already in use\|port.*already.*use"; then
        log_warning "Port conflict detected, killing existing process..."
        pkill -f "python.*app.py\|python.*main.py\|flask run" 2>/dev/null
        sleep 2
        fixed=1
    fi
    
    # Fix 4: Missing requirements.txt packages
    if [ -f "requirements.txt" ] && echo "$error_log" | grep -qi "ModuleNotFoundError"; then
        log_warning "Reinstalling all requirements..."
        pip3 install -q -r requirements.txt
        fixed=1
    fi
    
    # Fix 5: Database not initialized
    if echo "$error_log" | grep -qi "no such table\|OperationalError.*table"; then
        log_warning "Database not initialized, attempting to create tables..."
        if [ -f "manage.py" ]; then
            python3 manage.py migrate --noinput 2>/dev/null
        fi
        fixed=1
    fi
    
    return $fixed
}

# Run Django project with auto-healing
run_django() {
    install_python
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        log_info "📦 Installing Python dependencies..."
        pip3 install -q -r requirements.txt 2>/dev/null || log_warning "Some dependencies failed"
        
        log_info "🔄 Running migrations..."
        python3 manage.py migrate --noinput 2>/dev/null || log_warning "Migrations skipped"
        
        python3 manage.py collectstatic --noinput 2>/dev/null || log_warning "Static files skipped"
        
        log_info "🚀 Starting Django server on 0.0.0.0:5000 (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
        
        ERROR_LOG=$(mktemp)
        python3 manage.py runserver 0.0.0.0:5000 2>&1 | tee "$ERROR_LOG" &
        SERVER_PID=$!
        
        sleep 5
        
        if kill -0 $SERVER_PID 2>/dev/null; then
            log_success "Django server running!"
            wait $SERVER_PID
            exit 0
        else
            log_error "Django server crashed, analyzing..."
            ERROR_CONTENT=$(cat "$ERROR_LOG")
            
            if auto_fix_python_errors "$ERROR_CONTENT"; then
                log_success "Applied auto-fix, retrying..."
                RETRY_COUNT=$((RETRY_COUNT + 1))
            else
                log_error "No auto-fix available"
                cat "$ERROR_LOG"
                exit 1
            fi
        fi
    done
    
    log_error "Max retries reached"
    exit 1
}

# Run Flask application with auto-healing
run_flask() {
    install_python
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if [ -f "requirements.txt" ]; then
            log_info "📦 Installing Python dependencies..."
            pip3 install -q -r requirements.txt 2>/dev/null || log_warning "Some dependencies failed"
        fi
        
        MAIN_FILE=""
        for name in app.py main.py application.py run.py; do
            if [ -f "$name" ]; then
                MAIN_FILE="$name"
                break
            fi
        done
        
        if [ -z "$MAIN_FILE" ]; then
            log_error "No Flask entry point found"
            exit 1
        fi
        
        log_info "🔧 Pre-flight checks..."
        if grep -q "@app.before_first_request" "$MAIN_FILE"; then
            log_warning "Fixing deprecated syntax..."
            sed -i 's/@app\.before_first_request/# @app.before_first_request (deprecated)/g' "$MAIN_FILE"
            if grep -q "db.create_all()" "$MAIN_FILE"; then
                sed -i '/^app = Flask/a\\nwith app.app_context():\n    db.create_all()' "$MAIN_FILE"
            fi
        fi
        
        log_info "🚀 Starting Flask server: $MAIN_FILE on port 5000 (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
        
        ERROR_LOG=$(mktemp)
        python3 "$MAIN_FILE" 2>&1 | tee "$ERROR_LOG" &
        SERVER_PID=$!
        
        sleep 5
        
        if kill -0 $SERVER_PID 2>/dev/null; then
            log_success "Flask server running!"
            wait $SERVER_PID
            exit 0
        else
            log_error "Flask server crashed, analyzing..."
            ERROR_CONTENT=$(cat "$ERROR_LOG")
            
            if auto_fix_python_errors "$ERROR_CONTENT"; then
                log_success "Applied auto-fix, retrying..."
                RETRY_COUNT=$((RETRY_COUNT + 1))
            else
                log_error "No auto-fix available"
                cat "$ERROR_LOG"
                exit 1
            fi
        fi
    done
    
    log_error "Max retries reached"
    exit 1
}

# Run Node.js project
run_nodejs() {
    install_nodejs
    
    log_info "📦 Installing Node.js dependencies..."
    npm install --silent
    
    if [ -f "package.json" ]; then
        if grep -q '"dev"' package.json; then
            log_info "🚀 Starting with: npm run dev"
            exec npm run dev
        elif grep -q '"start"' package.json; then
            log_info "🚀 Starting with: npm start"
            exec npm start
        else
            MAIN=$(node -p "require('./package.json').main || 'index.js'")
            log_info "🚀 Starting with: node $MAIN"
            exec node "$MAIN"
        fi
    fi
}

# Run Python application
run_python() {
    install_python
    
    if [ -f "requirements.txt" ]; then
        log_info "📦 Installing Python dependencies..."
        pip3 install -q -r requirements.txt
    fi
    
    MAIN_FILE=""
    for file in main.py app.py run.py server.py; do
        if [ -f "$file" ]; then
            MAIN_FILE="$file"
            break
        fi
    done
    
    if [ -z "$MAIN_FILE" ]; then
        MAIN_FILE=$(ls *.py 2>/dev/null | head -n 1)
    fi
    
    if [ -z "$MAIN_FILE" ]; then
        log_error "No Python entry point found"
        exit 1
    fi
    
    log_info "🚀 Starting Python app: $MAIN_FILE"
    exec python3 "$MAIN_FILE"
}

# Run static HTML
run_static() {
    install_python
    
    log_info "🚀 Starting HTTP server on port 5000"
    exec python3 -m http.server 5000 --bind 0.0.0.0
}

# Main execution
cd /app

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
        log_error "Cannot determine how to run this project"
        log_info "📋 Files in workspace:"
        ls -la
        exit 1
        ;;
esac
