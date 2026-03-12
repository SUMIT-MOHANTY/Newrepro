# Quick Setup Guide for Bourtec VibeCoding

## Prerequisites
- Python 3.9 or higher
- Node.js 16 or higher
- npm or yarn
- Anthropic API key (get from https://console.anthropic.com/)

## Quick Start (Windows)

### Step 1: Backend Setup
```bash
cd vibecoding\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Configure API Key
1. Copy `.env.example` to `.env`
2. Open `.env` and add your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
   ```

### Step 3: Frontend Setup
```bash
cd ..\frontend
npm install
```

### Step 4: Run the Application
From the `vibecoding` directory:
```bash
start.bat
```

This will start both backend (port 8000) and frontend (port 3000).

## Manual Start

### Start Backend
```bash
cd vibecoding\backend
venv\Scripts\activate
python main.py
```

### Start Frontend (in new terminal)
```bash
cd vibecoding\frontend
npm run dev
```

## Access the Application
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Troubleshooting

### Port Already in Use
If ports 3000 or 8000 are in use:
- Backend: Edit `main.py` and change the port in `uvicorn.run()`
- Frontend: Edit `vite.config.js` and change the port in server config

### API Key Issues
Make sure your `.env` file has the correct API key format:
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx
```

### Module Not Found
Make sure you activated the virtual environment:
```bash
cd backend
venv\Scripts\activate
```

## Features to Try

1. **Calculator App**: "Create a modern calculator with dark theme"
2. **Todo List**: "Build a todo list with add, delete, and mark complete"
3. **Dashboard**: "Create a dashboard with charts and statistics"
4. **Landing Page**: "Make a landing page for a SaaS product"
5. **Form**: "Build a contact form with validation"

Enjoy building with AI! 🚀
