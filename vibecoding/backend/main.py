from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid
import re as _re
from dotenv import load_dotenv
from ai_config import ai_config
from project_manager import project_manager
from web_tools import make_request_with_tools

load_dotenv()

app = FastAPI(title="Bourtec VibeCoding API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    role: str
    content: str
    code: Optional[str] = None

class GenerateRequest(BaseModel):
    prompt: str
    history: List[Message] = []
    project_id: Optional[str] = None

class GenerateResponse(BaseModel):
    message: str
    code: Optional[str] = None
    project_id: str
    version_id: Optional[str] = None
    preview_url: Optional[str] = None
    tool_calls_log: Optional[List[dict]] = None

class ProjectCreateRequest(BaseModel):
    name: Optional[str] = None

class ProjectResponse(BaseModel):
    project_id: str
    name: str
    created_at: str
    versions: List[dict]
    current_version: Optional[str] = None

class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]

# AI Configuration is now handled by ai_config.py

SYSTEM_PROMPT = """You are an expert full-stack developer and AI assistant for Bourtec VibeCoding platform.
Your role is to help users build web applications, components, and interfaces through natural language.

🌐 WEB TOOLS AVAILABLE:
You have access to web tools that you can call dynamically:
1. **web_search(query)** - Search the web using DuckDuckGo to find documentation, tutorials, examples, API references, or any real-time information.
2. **fetch_page_content(url)** - Fetch and read the content of any web page to get detailed information, code examples, or documentation.

Use these tools when:
- The user asks about a library, API, or tool you're not sure about
- You need current documentation or latest versions of packages
- The user asks you to research something before building
- You need to verify API endpoints, syntax, or best practices
- The user explicitly asks you to search the web

🚨 CRITICAL RULES - NEVER BREAK THESE:
1. ALWAYS generate MULTIPLE files with file markers - NEVER just one file
2. ALWAYS include ALL necessary files (HTML, CSS, JS, config files, etc.)
3. ALWAYS write ACTUAL CODE in every file - NEVER descriptions or comments only
4. ALWAYS use file markers: // FILE: path/to/filename.ext
5. MINIMUM 4 files for any project (main file + templates/components + styles + config)

CRITICAL: Generate ACTUAL CODE for EVERY FILE, not folder structure descriptions or comments!

FILE MARKER FORMAT:
Use this EXACT format to separate files:
// FILE: path/to/filename.ext

Then immediately write the ACTUAL CODE for that file. NO descriptions, NO folder trees, ONLY CODE.

EXAMPLE - Flask Landing Page:

// FILE: app.py
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

// FILE: requirements.txt
Flask==2.3.0
Werkzeug==2.3.0

// FILE: templates/index.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Beautiful Landing Page</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <div class="hero">
        <h1>Welcome to Our Amazing Product</h1>
        <p>Transform your business with our innovative solution</p>
        <button class="cta-button">Get Started</button>
    </div>
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>

// FILE: templates/about.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>About Us</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <h1>About Us</h1>
    <p>We are a team of passionate developers.</p>
</body>
</html>

// FILE: static/css/style.css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
}

.hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    color: white;
    padding: 20px;
}

.hero h1 {
    font-size: 3rem;
    margin-bottom: 1rem;
    animation: fadeInUp 1s ease;
}

.hero p {
    font-size: 1.5rem;
    margin-bottom: 2rem;
    opacity: 0.9;
}

.cta-button {
    padding: 15px 40px;
    font-size: 1.2rem;
    background: white;
    color: #667eea;
    border: none;
    border-radius: 50px;
    cursor: pointer;
    transition: transform 0.3s ease;
}

.cta-button:hover {
    transform: scale(1.05);
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

// FILE: static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    const button = document.querySelector('.cta-button');
    
    button.addEventListener('click', function() {
        alert('Welcome! Let\\'s get started!');
    });
    
    // Smooth scroll effect
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
});

MINIMUM FILES REQUIRED FOR FLASK:
- app.py (main application)
- requirements.txt (dependencies)
- At least 1 HTML template in templates/
- At least 1 CSS file in static/css/
- At least 1 JS file in static/js/ (even if simple)
TOTAL: MINIMUM 5 FILES

EXAMPLE - Django Project:

// FILE: manage.py
#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Couldn't import Django.") from exc
    execute_from_command_line(sys.argv)

// FILE: myproject/settings.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-your-secret-key-here'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'myapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

// FILE: myproject/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('myapp.urls')),
]

// FILE: myproject/__init__.py
# Django project initialization

// FILE: myapp/models.py
from django.db import models

class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title

// FILE: myapp/views.py
from django.shortcuts import render
from .models import Post

def home(request):
    posts = Post.objects.all()
    return render(request, 'myapp/home.html', {'posts': posts})

def about(request):
    return render(request, 'myapp/about.html')

// FILE: myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
]

// FILE: myapp/__init__.py
# App initialization

// FILE: myapp/admin.py
from django.contrib import admin
from .models import Post

admin.site.register(Post)

// FILE: myapp/apps.py
from django.apps import AppConfig

class MyappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'myapp'

// FILE: myapp/templates/myapp/home.html
<!DOCTYPE html>
<html>
<head>
    <title>Home</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <h1>Welcome to Django</h1>
    <div class="posts">
        {% for post in posts %}
        <div class="post">
            <h2>{{ post.title }}</h2>
            <p>{{ post.content }}</p>
        </div>
        {% endfor %}
    </div>
</body>
</html>

// FILE: myapp/templates/myapp/about.html
<!DOCTYPE html>
<html>
<head>
    <title>About</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <h1>About Us</h1>
    <p>This is a Django application.</p>
</body>
</html>

// FILE: myapp/static/css/style.css
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    background: #f5f5f5;
}

h1 {
    color: #333;
}

.posts {
    display: grid;
    gap: 20px;
}

.post {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

// FILE: requirements.txt
Django==4.2.0
asgiref==3.7.0
sqlparse==0.4.4

MINIMUM FILES REQUIRED FOR DJANGO:
- manage.py
- myproject/settings.py
- myproject/urls.py
- myproject/__init__.py
- myapp/models.py
- myapp/views.py
- myapp/urls.py
- myapp/__init__.py
- myapp/admin.py
- myapp/apps.py
- At least 1 HTML template
- At least 1 CSS file
- requirements.txt
TOTAL: MINIMUM 13 FILES

EXAMPLE - React Todo App:

// FILE: app.py
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

// FILE: requirements.txt
Flask==2.3.0
Werkzeug==2.3.0

// FILE: templates/index.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Beautiful Landing Page</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <div class="hero">
        <h1>Welcome to Our Amazing Product</h1>
        <p>Transform your business with our innovative solution</p>
        <button class="cta-button">Get Started</button>
    </div>
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>

// FILE: templates/about.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>About Us</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <h1>About Us</h1>
    <p>We are a team of passionate developers.</p>
</body>
</html>

// FILE: static/css/style.css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
}

.hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    color: white;
    padding: 20px;
}

.hero h1 {
    font-size: 3rem;
    margin-bottom: 1rem;
    animation: fadeInUp 1s ease;
}

.hero p {
    font-size: 1.5rem;
    margin-bottom: 2rem;
    opacity: 0.9;
}

.cta-button {
    padding: 15px 40px;
    font-size: 1.2rem;
    background: white;
    color: #667eea;
    border: none;
    border-radius: 50px;
    cursor: pointer;
    transition: transform 0.3s ease;
}

.cta-button:hover {
    transform: scale(1.05);
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

// FILE: static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    const button = document.querySelector('.cta-button');
    
    button.addEventListener('click', function() {
        alert('Welcome! Let\\'s get started!');
    });
    
    // Smooth scroll effect
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
});

EXAMPLE - React Todo App:

// FILE: package.json
{
  "name": "react-todo-app",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build"
  }
}

// FILE: public/index.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Todo App</title>
</head>
<body>
    <div id="root"></div>
</body>
</html>

// FILE: src/index.js
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// FILE: src/App.js
import React, { useState } from 'react';
import './App.css';
import TodoList from './components/TodoList';
import AddTodo from './components/AddTodo';

function App() {
  const [todos, setTodos] = useState([
    { id: 1, text: 'Learn React', completed: false },
    { id: 2, text: 'Build Todo App', completed: false }
  ]);

  const addTodo = (text) => {
    const newTodo = {
      id: Date.now(),
      text: text,
      completed: false
    };
    setTodos([...todos, newTodo]);
  };

  const toggleTodo = (id) => {
    setTodos(todos.map(todo =>
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    ));
  };

  const deleteTodo = (id) => {
    setTodos(todos.filter(todo => todo.id !== id));
  };

  return (
    <div className="App">
      <h1>My Todo List</h1>
      <AddTodo onAdd={addTodo} />
      <TodoList todos={todos} onToggle={toggleTodo} onDelete={deleteTodo} />
    </div>
  );
}

export default App;

// FILE: src/components/TodoList.js
import React from 'react';
import TodoItem from './TodoItem';

function TodoList({ todos, onToggle, onDelete }) {
  return (
    <div className="todo-list">
      {todos.map(todo => (
        <TodoItem
          key={todo.id}
          todo={todo}
          onToggle={onToggle}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

export default TodoList;

// FILE: src/components/TodoItem.js
import React from 'react';

function TodoItem({ todo, onToggle, onDelete }) {
  return (
    <div className="todo-item">
      <input
        type="checkbox"
        checked={todo.completed}
        onChange={() => onToggle(todo.id)}
      />
      <span style={{ textDecoration: todo.completed ? 'line-through' : 'none' }}>
        {todo.text}
      </span>
      <button onClick={() => onDelete(todo.id)}>Delete</button>
    </div>
  );
}

export default TodoItem;

// FILE: src/components/AddTodo.js
import React, { useState } from 'react';

function AddTodo({ onAdd }) {
  const [text, setText] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (text.trim()) {
      onAdd(text);
      setText('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="add-todo">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Add new todo..."
      />
      <button type="submit">Add</button>
    </form>
  );
}

export default AddTodo;

// FILE: src/App.css
.App {
  max-width: 600px;
  margin: 50px auto;
  padding: 20px;
  font-family: Arial, sans-serif;
}

h1 {
  text-align: center;
  color: #333;
}

.add-todo {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.add-todo input {
  flex: 1;
  padding: 10px;
  border: 2px solid #ddd;
  border-radius: 5px;
  font-size: 16px;
}

.add-todo button {
  padding: 10px 20px;
  background: #4CAF50;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: #f9f9f9;
  margin-bottom: 10px;
  border-radius: 5px;
}

.todo-item button {
  margin-left: auto;
  padding: 5px 10px;
  background: #f44336;
  color: white;
  border: none;
  border-radius: 3px;
  cursor: pointer;
}

// FILE: src/index.css
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: #f0f0f0;
}

CRITICAL RULES:
1. ALWAYS use file markers: // FILE: path/to/file.ext
2. Write ACTUAL CODE after each marker, not descriptions
3. NO folder structure diagrams in the code
4. NO comments like "# Flask application entry point" as the only content
5. Every file must have COMPLETE, WORKING code
6. Include ALL necessary files (HTML, CSS, JS, config files)
7. Make code production-ready and fully functional
8. NEVER write folder trees like "flask-landing/ │ ├─ app.py"

IMPORTANT FOR REACT/VUE/ANGULAR APPS:
For React/Vue/Angular apps, ALSO include a standalone HTML preview file that works without build tools:
- Create a file: public/preview.html or preview.html
- Use CDN links for React/Vue/Angular (no build required)
- Include all components inline or via CDN
- This allows immediate preview without npm install/build

Example React with Preview:
```
// FILE: package.json
{...}

// FILE: public/index.html
<!DOCTYPE html>
<html>
<head><title>React App</title></head>
<body><div id="root"></div></body>
</html>

// FILE: public/preview.html
<!DOCTYPE html>
<html>
<head>
    <title>React App Preview</title>
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
        /* Include all CSS inline */
        body { margin: 0; font-family: Arial; }
        .hero { text-align: center; padding: 50px; }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        // Include all React components inline
        function Hero() {
            return (
                <div className="hero">
                    <h1>Welcome</h1>
                    <button>Get Started</button>
                </div>
            );
        }
        
        function App() {
            return <Hero />;
        }
        
        ReactDOM.render(<App />, document.getElementById('root'));
    </script>
</body>
</html>

// FILE: src/App.js
import React from 'react';
import Hero from './components/Hero';
function App() {
    return <Hero />;
}
export default App;

// FILE: src/components/Hero.js
import React from 'react';
function Hero() {
    return (
        <div className="hero">
            <h1>Welcome</h1>
            <button>Get Started</button>
        </div>
    );
}
export default Hero;
```

This way:
- preview.html works immediately in browser (no build needed)
- src/ files are proper React code for development
- Users can see preview instantly AND have proper React structure

CDN LINKS:
- NEVER include integrity or crossorigin attributes
- Use simple CDN links: <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">

Response format:
1. Brief explanation (1-2 sentences)
2. Complete code with file markers
3. NO folder structure diagrams"""

@app.get("/")
async def root():
    return {"message": "Bourtec VibeCoding API is running"}

@app.post("/api/generate", response_model=GenerateResponse)
async def generate_code(request: GenerateRequest):
    # Get or create project ID at the start
    project_id = request.project_id or project_manager.generate_project_id()
    
    try:
        # Build conversation history with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in request.history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current prompt with a strict tool-calling enforcement
        prompt_with_instructions = request.prompt
        if any(word in request.prompt.lower() for word in ['search', 'web', 'internet', 'look up', 'fetch', 'url', 'http']):
            prompt_with_instructions += "\n\n(IMPORTANT: Use your `web_search` or `fetch_page_content` tool to fulfill this request. DO NOT say you cannot browse the web. You HAVE the ability via function calling.)"
            
        messages.append({
            "role": "user",
            "content": prompt_with_instructions
        })

        # Call AI API with function calling support (web search + page fetch)
        response = await make_request_with_tools(messages)
        
        # Extract tool calls log if any tools were used
        tool_calls_log = response.pop("_tool_calls_log", None)
        
        # Extract AI response
        if "choices" in response and len(response["choices"]) > 0:
            ai_response = response["choices"][0]["message"].get("content") or ""
        else:
            raise Exception("Invalid response format from AI API")

        # Extract code if present
        code = None
        if "```python" in ai_response:
            code_start = ai_response.find("```python") + 10
            code_end = ai_response.find("```", code_start)
            code = ai_response[code_start:code_end].strip()
        elif "```html" in ai_response:
            code_start = ai_response.find("```html") + 7
            code_end = ai_response.find("```", code_start)
            code = ai_response[code_start:code_end].strip()
        elif "```" in ai_response:
            code_start = ai_response.find("```") + 3
            code_end = ai_response.find("```", code_start)
            code = ai_response[code_start:code_end].strip()
        
        # Validate that code has multiple files with file markers
        if code:
            file_marker_count = len(_re.findall(r'//\s*FILE:\s*|#\s*FILE:\s*|<!--\s*FILE:\s*', code))
            
            # If less than 3 file markers, regenerate with stronger prompt
            if file_marker_count < 3:
                print(f"⚠️ Warning: Only {file_marker_count} files detected. Requesting complete structure...")
                
                # Add a follow-up message demanding complete structure
                messages.append({
                    "role": "assistant",
                    "content": ai_response
                })
                messages.append({
                    "role": "user",
                    "content": f"""Please provide a COMPLETE project structure with ALL necessary files.

REQUIRED:
- Use file markers: // FILE: path/to/file.ext
- Include MINIMUM 5 files:
  1. Main application file
  2. Configuration/dependencies file (requirements.txt, package.json, etc.)
  3. At least 2 template/component files
  4. At least 1 CSS file
  5. At least 1 JavaScript file (if applicable)

Generate the COMPLETE structure with ACTUAL CODE in every file."""
                })
                
                # Make another API call (without tools for the follow-up)
                response = ai_config.make_request(messages)
                if "choices" in response and len(response["choices"]) > 0:
                    ai_response = response["choices"][0]["message"]["content"]
                    
                    # Re-extract code
                    if "```python" in ai_response:
                        code_start = ai_response.find("```python") + 10
                        code_end = ai_response.find("```", code_start)
                        code = ai_response[code_start:code_end].strip()
                    elif "```html" in ai_response:
                        code_start = ai_response.find("```html") + 7
                        code_end = ai_response.find("```", code_start)
                        code = ai_response[code_start:code_end].strip()
                    elif "```" in ai_response:
                        code_start = ai_response.find("```") + 3
                        code_end = ai_response.find("```", code_start)
                        code = ai_response[code_start:code_end].strip()
        
        # Clean up integrity and crossorigin attributes from CDN links
        if code:
            import re
            # Remove integrity attributes
            code = re.sub(r'\s+integrity="[^"]*"', '', code)
            code = re.sub(r"\s+integrity='[^']*'", '', code)
            # Remove crossorigin attributes
            code = re.sub(r'\s+crossorigin="[^"]*"', '', code)
            code = re.sub(r"\s+crossorigin='[^']*'", '', code)
            code = re.sub(r'\s+crossorigin(?=\s|>)', '', code)
        
        # Initialize message variable
        message = ai_response
        
        # Check if AI returned instructions instead of actual code
        if code and (
            not code.strip().startswith(('from', 'import', 'def', 'class', 'app =', '<!DOCTYPE', '<html', 'from flask')) and
            len(code.strip().split('\n')) < 5
        ):
            # This looks like instructions, not actual code
            code = None
            message = ai_response  # Show full response including instructions

        # Clean message (remove code blocks)
        if code:
            message = ai_response.split("```")[0].strip()

        # Save code version if code was generated
        version_id = None
        preview_url = None
        
        if code:
            version_id, _ = project_manager.save_code_version(project_id, code, request.prompt)
            
            # Check if Docker is available before attempting to create container
            if project_manager.docker_client is None:
                print("⚠️ Docker not available - preview functionality disabled")
                print("Please ensure Docker Desktop is installed and running")
                preview_url = None
            else:
                # Create container for preview
                try:
                    preview_url = await project_manager.create_container_for_code(project_id, version_id)
                except Exception as e:
                    print(f"Failed to create container: {str(e)}")
                    # Continue without container if it fails

        return GenerateResponse(
            message=message if message else "I've generated the code for you!",
            code=code,
            project_id=project_id,
            version_id=version_id,
            preview_url=preview_url,
            tool_calls_log=tool_calls_log
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return error response with valid project_id
        return GenerateResponse(
            message=f"I encountered an error: {str(e)}. Please try again or rephrase your request.",
            code=None,
            project_id=project_id,
            version_id=None,
            preview_url=None,
            tool_calls_log=None
        )

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

# Project Management Endpoints

@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(request: ProjectCreateRequest):
    try:
        project_id = project_manager.generate_project_id()
        project_dir = project_manager.create_project_directory(project_id)
        
        project_info = project_manager.get_project_info(project_id)
        project_info["name"] = request.name or f"Project {project_id[:8]}"
        
        # Update project metadata with name
        with open(project_dir / "metadata.json", "w") as f:
            import json
            json.dump(project_info, f, indent=2)
        
        return ProjectResponse(**project_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects", response_model=ProjectListResponse)
async def list_projects():
    try:
        projects = project_manager.list_projects()
        return ProjectListResponse(projects=projects)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    try:
        project_info = project_manager.get_project_info(project_id)
        if not project_info:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectResponse(**project_info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/versions/{version_id}/code")
async def get_version_code(project_id: str, version_id: str):
    try:
        code = project_manager.get_version_code(project_id, version_id)
        if not code:
            raise HTTPException(status_code=404, detail="Version not found")
        return {"code": code}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/versions/{version_id}/preview")
async def create_preview(project_id: str, version_id: str):
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            raise HTTPException(
                status_code=503,
                detail="Docker not available. Please ensure Docker Desktop is installed and running."
            )
        
        preview_url = await project_manager.create_container_for_code(project_id, version_id)
        if not preview_url:
            raise HTTPException(status_code=500, detail="Failed to create preview")
        return {"preview_url": preview_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/projects/{project_id}/versions/{version_id}/preview")
async def stop_preview(project_id: str, version_id: str):
    try:
        project_manager.stop_container(project_id, version_id)
        return {"message": "Preview stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/download")
async def download_project(project_id: str):
    try:
        zip_path = project_manager.create_project_zip(project_id)
        if not zip_path:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return FileResponse(
            path=str(zip_path),
            filename=f"{project_id}_complete.zip",
            media_type="application/zip"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup")
async def cleanup_containers():
    try:
        # Check if Docker is available
        if project_manager.docker_client is None:
            return {"message": "Docker not available - no containers to clean up"}
        
        project_manager.cleanup_old_containers()
        return {"message": "Cleanup completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
