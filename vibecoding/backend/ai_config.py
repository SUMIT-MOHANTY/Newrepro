import os
from typing import Dict, Any, List
import requests
from dotenv import load_dotenv

load_dotenv()

class AIConfig:
    """Global AI configuration manager"""
    
    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY")
        if not self.api_key:
            raise ValueError("AI_API_KEY environment variable is required")
        
        self.base_url = os.getenv("AI_BASE_URL")
        if not self.base_url:
            raise ValueError("AI_BASE_URL environment variable is required")
        
        self.model = os.getenv("AI_MODEL")
        if not self.model:
            raise ValueError("AI_MODEL environment variable is required")
        
        self.max_tokens = int(os.getenv("AI_MAX_TOKENS", "4096"))
        self.temperature = float(os.getenv("AI_TEMPERATURE", "1.0"))
        self.top_p = float(os.getenv("AI_TOP_P", "1.0"))
        self.frequency_penalty = float(os.getenv("AI_FREQUENCY_PENALTY", "0.0"))
        self.presence_penalty = float(os.getenv("AI_PRESENCE_PENALTY", "0.0"))
        self.stream = os.getenv("AI_STREAM", "false").lower() == "true"
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers for the AI API"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def get_payload(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Get request payload for the AI API"""
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.presence_penalty),
            "stream": kwargs.get("stream", self.stream)
        }
        return payload
    
    def make_request(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Make API request to the AI service"""
        headers = self.get_headers()
        payload = self.get_payload(messages, **kwargs)
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"AI API request failed: {str(e)}")

# Global AI configuration instance
ai_config = AIConfig()
