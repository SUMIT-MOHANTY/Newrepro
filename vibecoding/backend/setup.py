#!/usr/bin/env python3
"""
VibeCoding Development Server Setup
Similar to Flask setup but for our container-based system
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python 3.8+ is installed"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]} detected")

def create_virtual_env():
    """Create virtual environment"""
    venv_path = Path("venv")
    
    if venv_path.exists():
        print("📁 Virtual environment already exists")
        return
    
    print("🔧 Creating virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("✅ Virtual environment created successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create virtual environment: {e}")
        sys.exit(1)

def activate_venv_instructions():
    """Show activation instructions"""
    if os.name == 'nt':  # Windows
        activate_cmd = "venv\\Scripts\\activate"
        pip_cmd = "venv\\Scripts\\pip"
    else:  # Linux/Mac
        activate_cmd = "source venv/bin/activate"
        pip_cmd = "venv/bin/pip"
    
    print("\n📋 Setup Instructions:")
    print(f"1. Activate virtual environment: {activate_cmd}")
    print(f"2. Install dependencies: {pip_cmd} install -r requirements.txt")
    print("3. Start server: python main.py")
    print("4. Open browser: http://127.0.0.1:8000")

def install_dependencies():
    """Install required dependencies"""
    requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print("❌ requirements.txt not found")
        return
    
    print("📦 Installing dependencies...")
    try:
        # Check if in virtual environment
        if 'venv' not in sys.executable:
            print("⚠️  Please activate virtual environment first")
            activate_venv_instructions()
            return
        
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], check=True)
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")

def setup_docker():
    """Setup Docker for code execution"""
    print("🐳 Setting up Docker environment...")
    
    docker_files = [
        "Dockerfile.code-executor",
        "build-docker.bat" if os.name == 'nt' else "build-docker.sh"
    ]
    
    for docker_file in docker_files:
        if Path(docker_file).exists():
            print(f"✅ Found {docker_file}")
        else:
            print(f"❌ Missing {docker_file}")
    
    # Try to build Docker image
    build_script = "build-docker.bat" if os.name == 'nt' else "./build-docker.sh"
    if Path(build_script).exists():
        print("🔨 Building Docker image...")
        try:
            subprocess.run(build_script, check=True, shell=True)
            print("✅ Docker image built successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to build Docker image: {e}")

def start_server():
    """Start the development server"""
    print("🚀 Starting VibeCoding server...")
    
    if not Path("main.py").exists():
        print("❌ main.py not found")
        return
    
    try:
        subprocess.run([sys.executable, "main.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start server: {e}")
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")

def main():
    """Main setup function"""
    print("🎯 VibeCoding Development Setup")
    print("=" * 40)
    
    # Check Python version
    check_python_version()
    
    # Create virtual environment
    create_virtual_env()
    
    # Show activation instructions
    activate_venv_instructions()
    
    # Setup Docker if files exist
    setup_docker()
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Activate virtual environment")
    print("2. Install dependencies") 
    print("3. Start server")
    print("4. Open http://127.0.0.1:8000")
    
    # Ask if user wants to start server
    try:
        start = input("\n🚀 Start server now? (y/n): ").lower().strip()
        if start in ['y', 'yes']:
            start_server()
    except KeyboardInterrupt:
        print("\n👋 Setup completed!")

if __name__ == "__main__":
    main()
