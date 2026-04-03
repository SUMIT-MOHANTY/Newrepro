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
        
        prompt = f"""Analyze the following user message and classify it into ONE of two categories:

1. 'CODE': If the user is EXPLICITLY asking to build, create, generate, modify, implement, fix, debug, repair, update, or troubleshoot a project, software, script, or application.
2. 'CHAT': If the user is JUST greeting you (e.g., 'Hi', 'Hello'), asking a general question, seeking an explanation, or having a casual conversation without explicit code instructions.

USER MESSAGE: "{message}"

Return ONLY the word 'CODE' or 'CHAT'. No other text. If the message is ambiguous or purely conversational, choose 'CHAT'."""

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

