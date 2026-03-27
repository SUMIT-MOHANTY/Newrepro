import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "agent_service.txt")
LOG_FILE_2 = os.path.join(LOG_DIR, "ai_service.txt")

def log_llm_interaction(messages, response):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
            
            f.write("\n--- SYSTEM / INPUT MESSAGES ---\n")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"[{role.upper()}]:\n{content}\n\n")
            
            f.write("\n--- AI RESPONSE ---\n")
            f.write(response if isinstance(response, str) else str(response))
            f.write("\n" + "="*80 + "\n")
    except Exception as e:
        print(f"[LOG ERROR] Failed to write LLM log: {e}")

def log_llm_interaction_ai_service(messages, response):
    try:
        with open(LOG_FILE_2, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
            
            f.write("\n--- SYSTEM / INPUT MESSAGES ---\n")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"[{role.upper()}]:\n{content}\n\n")
            
            f.write("\n--- AI RESPONSE ---\n")
            f.write(response if isinstance(response, str) else str(response))
            f.write("\n" + "="*80 + "\n")
    except Exception as e:
        print(f"[LOG ERROR] Failed to write LLM log: {e}")