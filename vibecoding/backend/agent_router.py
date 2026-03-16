"""
Agent Router - Decides which agent to use
"""
import re
import logging
from typing import Dict, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes user messages to appropriate agent using AI classification"""
    
    @classmethod
    async def route(cls, message: str) -> Tuple[str, float]:
        """
        Determine which agent should handle the message using an LLM call.
        """
        from ai_config import ai_config
        
        # Guard for very short greetings/greetings
        greetings = ['hi', 'hello', 'hey', 'thanks', 'thank you']
        if message.lower().strip() in greetings:
            return 'chat', 1.0

        prompt = f"""Classify the following user message into ONE of two categories:
1. 'CODE': If the user is asking to build, create, generate, modify, or implement a project, app, software, or script.
2. 'CHAT': If the user is asking a general question, seeking an explanation, or just having a conversation.

USER MESSAGE: "{message}"

Return ONLY the word 'CODE' or 'CHAT'. No other text."""

        try:
            # Using a very low max_tokens for speed
            response = ai_config.make_request([
                {"role": "system", "content": "You are a routing assistant. Respond with 'CODE' or 'CHAT' only."},
                {"role": "user", "content": prompt}
            ])
            
            result = ""
            if "choices" in response and len(response["choices"]) > 0:
                result = response["choices"][0]["message"].get("content", "").upper()
            
            if 'CODE' in result:
                return 'code', 0.9
            else:
                return 'chat', 0.9

        except Exception as e:
            logger.error(f"Router AI error: {e}")
            # Fallback to a very basic keyword check if AI fails
            if any(k in message.lower() for k in ['create', 'build', 'make', 'generate', 'code', 'app']):
                return 'code', 0.5
            return 'chat', 0.5

    @classmethod
    async def is_code_request(cls, message: str) -> bool:
        """Simple boolean check if message is a code request"""
        agent_type, _ = await cls.route(message)
        return agent_type == 'code'

