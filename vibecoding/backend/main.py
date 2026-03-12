from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv
from ai_config import ai_config

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

class GenerateResponse(BaseModel):
    message: str
    code: Optional[str] = None

# AI Configuration is now handled by ai_config.py

SYSTEM_PROMPT = """You are an expert full-stack developer and AI assistant for Bourtec VibeCoding platform.
Your role is to help users build web applications, components, and interfaces through natural language.

When a user asks you to create something:
1. Generate complete, working HTML/CSS/JavaScript code
2. Make it visually appealing with modern design
3. Ensure it's fully functional and interactive
4. Use inline styles and scripts for simplicity (everything in one HTML file)
5. Support any language or framework the user requests
6. Add responsive design and good UX practices

Always respond with:
- A friendly explanation of what you created
- The complete code wrapped in a single HTML file

Make the code production-ready, beautiful, and functional."""

@app.get("/")
async def root():
    return {"message": "Bourtec VibeCoding API is running"}

@app.post("/api/generate", response_model=GenerateResponse)
async def generate_code(request: GenerateRequest):
    try:
        # Build conversation history with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in request.history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current prompt
        messages.append({
            "role": "user",
            "content": request.prompt
        })

        # Call AI API
        response = ai_config.make_request(messages)
        
        # Extract AI response
        if "choices" in response and len(response["choices"]) > 0:
            ai_response = response["choices"][0]["message"]["content"]
        else:
            raise Exception("Invalid response format from AI API")

        # Extract code if present
        code = None
        if "```html" in ai_response:
            code_start = ai_response.find("```html") + 7
            code_end = ai_response.find("```", code_start)
            code = ai_response[code_start:code_end].strip()
        elif "```" in ai_response:
            code_start = ai_response.find("```") + 3
            code_end = ai_response.find("```", code_start)
            code = ai_response[code_start:code_end].strip()

        # Clean message (remove code blocks)
        message = ai_response
        if code:
            message = ai_response.split("```")[0].strip()

        return GenerateResponse(
            message=message if message else "I've generated the code for you!",
            code=code
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
