"""
Agent Router - Decides which agent to use
"""
import re
import logging
from typing import Dict, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes user messages to appropriate agent"""
    
    # Keywords that indicate code generation request
    CODE_KEYWORDS = [
        'create', 'build', 'make', 'generate', 'develop',
        'code', 'app', 'application', 'website', 'web app',
        'api', 'backend', 'frontend', 'fullstack',
        'project', 'program', 'script', 'tool',
        'implement', 'write code', 'develop',
        'todo', 'calculator', 'dashboard', 'portal',
        'system', 'platform', 'service'
    ]
    
    # Phrases that indicate general chat
    CHAT_PHRASES = [
        'what is', 'what are', 'how does', 'how do',
        'explain', 'tell me about', 'difference between',
        'should i', 'which is better', 'recommend',
        'hello', 'hi', 'hey', 'thanks', 'thank you',
        'help', 'can you help'
    ]
    
    @classmethod
    def route(cls, message: str) -> Tuple[str, float]:
        """
        Determine which agent should handle the message
        
        Returns:
            Tuple of (agent_type, confidence)
            agent_type: 'code' or 'chat'
            confidence: 0.0 to 1.0
        """
        message_lower = message.lower()
        
        # Check for explicit code generation requests
        code_score = cls._calculate_code_score(message_lower)
        chat_score = cls._calculate_chat_score(message_lower)
        
        logger.info(f"Routing scores - Code: {code_score:.2f}, Chat: {chat_score:.2f}")
        
        if code_score > chat_score:
            return 'code', code_score
        else:
            return 'chat', chat_score
    
    @classmethod
    def _calculate_code_score(cls, message: str) -> float:
        """Calculate likelihood this is a code generation request"""
        score = 0.0
        
        # Check for code keywords
        for keyword in cls.CODE_KEYWORDS:
            if keyword in message:
                score += 0.3
        
        # Check for programming language mentions
        languages = ['python', 'javascript', 'java', 'go', 'rust', 'php', 'ruby', 'c++', 'c#']
        for lang in languages:
            if lang in message:
                score += 0.2
        
        # Check for framework mentions
        frameworks = ['flask', 'django', 'fastapi', 'react', 'vue', 'angular', 'express', 'nextjs']
        for fw in frameworks:
            if fw in message:
                score += 0.2
        
        # Check for action verbs
        action_verbs = ['create', 'build', 'make', 'develop', 'implement', 'write']
        for verb in action_verbs:
            if message.startswith(verb):
                score += 0.4
        
        return min(score, 1.0)
    
    @classmethod
    def _calculate_chat_score(cls, message: str) -> float:
        """Calculate likelihood this is a general chat request"""
        score = 0.0
        
        # Check for chat phrases
        for phrase in cls.CHAT_PHRASES:
            if phrase in message:
                score += 0.4
        
        # Check for question marks (usually questions, not code requests)
        if '?' in message and not any(kw in message for kw in ['how to create', 'how to build']):
            score += 0.3
        
        # Short messages are usually chat
        if len(message.split()) < 5:
            score += 0.2
        
        return min(score, 1.0)
    
    @classmethod
    def is_code_request(cls, message: str) -> bool:
        """Simple boolean check if message is a code request"""
        agent_type, confidence = cls.route(message)
        return agent_type == 'code' and confidence > 0.3


# Test the router
if __name__ == "__main__":
    test_messages = [
        "What is Flask?",
        "Create a todo app with Flask",
        "How does React work?",
        "Build a REST API with FastAPI",
        "Hello!",
        "Make a calculator in Python",
        "Explain the difference between Flask and Django",
        "Generate a dashboard with charts"
    ]
    
    for msg in test_messages:
        agent_type, confidence = AgentRouter.route(msg)
        print(f"{msg}")
        print(f"  → {agent_type.upper()} agent (confidence: {confidence:.2f})\n")
