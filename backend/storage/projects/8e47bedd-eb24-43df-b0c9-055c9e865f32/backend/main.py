from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

app = FastAPI(title="NexusDesk-v1 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "app": "NexusDesk-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": True
    }

@app.get("/api/v1/info")
def get_info():
    return {
        "project": "NexusDesk-v1",
        "engine": "FastAPI + Vite React",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
