# Bourtec VibeCoding

Build Apps with AI in Minutes - An AI-powered application builder for Bourtec organization.

## Features

- 🤖 AI-powered code generation using Claude
- 🎨 Live preview of generated applications
- 💬 Interactive chat interface
- 🌍 Multi-language support (any programming language)
- 📱 Responsive design
- ⚡ Real-time code execution
- 💾 Download generated code

## Tech Stack

### Frontend
- React 18
- Vite
- Tailwind CSS
- Axios
- Lucide React (icons)

### Backend
- FastAPI
- Python 3.9+
- Anthropic Claude API
- Uvicorn

## Setup Instructions

### Backend Setup

1. Navigate to backend directory:
```bash
cd vibecoding/backend
```

2. Create virtual environment:
```bash
python -m venv venv
```

3. Activate virtual environment:
- Windows: `venv\Scripts\activate`
- Mac/Linux: `source venv/bin/activate`

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create `.env` file:
```bash
cp .env.example .env
```

6. Add your Anthropic API key to `.env`:
```
ANTHROPIC_API_KEY=your_actual_api_key_here
```

7. Run the backend:
```bash
python main.py
```

Backend will run on http://localhost:8001

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd vibecoding/frontend
```

2. Install dependencies:
```bash
npm install
```

3. Copy logo from main project:
```bash
copy ..\..\frontend\src\assets\logo.png public\logo.png
```

4. Run the development server:
```bash
npm run dev
```

Frontend will run on http://localhost:3000

## Usage

1. Open http://localhost:3000 in your browser
2. Type what you want to build in the chat (e.g., "Create a calculator app")
3. Watch as the AI generates the code and displays it in the preview
4. Switch between Preview and Code tabs
5. Download the generated code if needed

## Example Prompts

- "Create a calculator app with modern design"
- "Build a todo list application"
- "Make a weather dashboard"
- "Create a landing page for a tech company"
- "Build a contact form with validation"

## API Endpoints

- `GET /` - Root endpoint
- `POST /api/generate` - Generate code from prompt
- `GET /api/health` - Health check

## License

© 2024 Bourtec Organization. All rights reserved.
