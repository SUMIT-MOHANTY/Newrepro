"""
Dual Agent Handler - Integrates Chat Agent and Code Execution Agent
"""
import logging
from typing import Dict, List
from agent_router import AgentRouter
from ai_agent_manager import get_agent_manager
from ai_config import ai_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DualAgentHandler:
    """Handles routing between chat and code execution agents"""
    
    def __init__(self):
        self.router = AgentRouter()
        self.agent_manager = get_agent_manager()
        self.agent_initialized = False
    
    async def handle_message(self, message: str, history: List[Dict] = None) -> Dict:
        """
        Route message to appropriate agent and return response
        
        Args:
            message: User's message
            history: Conversation history
        
        Returns:
            Dict with response data
        """
        history = history or []
        
        # Route the message
        agent_type, confidence = self.router.route(message)
        
        logger.info(f"📍 Routing to {agent_type.upper()} agent (confidence: {confidence:.2f})")
        
        if agent_type == 'code':
            return await self._handle_code_request(message, history)
        else:
            return await self._handle_chat_request(message, history)
    
    async def _handle_chat_request(self, message: str, history: List[Dict]) -> Dict:
        """Handle general chat using external AI (OpenAI/Anthropic)"""
        try:
            logger.info("💬 Processing with Chat Agent (outside container)")
            
            # Build messages for AI
            messages = []
            
            # Add system prompt for chat agent
            chat_system_prompt = """You are a helpful AI assistant for developers.
You answer questions about programming, explain concepts, provide advice, and have general conversations.

When users ask about programming concepts, frameworks, or tools, provide clear explanations.
If they ask for code examples, provide small snippets to illustrate concepts.

If a user asks you to BUILD, CREATE, or GENERATE a complete application, 
politely let them know that you can help with that, and they should ask more specifically."""
            
            messages.append({"role": "system", "content": chat_system_prompt})
            
            # Add history
            for msg in history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Call AI
            response = ai_config.make_request(messages)
            
            # Extract response
            if "choices" in response and len(response["choices"]) > 0:
                ai_response = response["choices"][0]["message"].get("content", "")
            else:
                ai_response = "I'm sorry, I couldn't process that request."
            
            return {
                "success": True,
                "agent_type": "chat",
                "message": ai_response,
                "code": None,
                "preview_url": None
            }
        
        except Exception as e:
            logger.error(f"Chat agent error: {e}")
            return {
                "success": False,
                "agent_type": "chat",
                "error": str(e),
                "message": "Sorry, I encountered an error processing your request."
            }
    
    async def _handle_code_request(self, message: str, history: List[Dict]) -> Dict:
        """Handle code generation using AI agent inside container"""
        try:
            logger.info("🔨 Processing with Code Execution Agent (inside container)")
            
            # Initialize agent container if not already running
            if not self.agent_initialized:
                logger.info("🚀 Starting AI agent container...")
                
                # Get API key from config
                api_key = ai_config.get_api_key()
                provider = "anthropic" if "anthropic" in ai_config.ai_api_url.lower() else "openai"
                
                agent_url = self.agent_manager.start_agent_container(api_key, provider)
                
                if not agent_url:
                    logger.error("Failed to start agent container")
                    # Fallback to chat agent
                    return await self._handle_chat_request(
                        f"I need to generate code for: {message}",
                        history
                    )
                
                self.agent_initialized = True
                logger.info(f"✅ Agent container ready at {agent_url}")
            
            # Send request to code execution agent
            logger.info("📤 Sending request to code execution agent...")
            result = self.agent_manager.send_request(message)
            
            if result.get("success"):
                return {
                    "success": True,
                    "agent_type": "code",
                    "message": result.get("message", "Code generated successfully!"),
                    "code": result.get("code"),
                    "preview_url": result.get("url"),
                    "project_dir": result.get("project_dir")
                }
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"Code agent failed: {error_msg}")
                
                # Get agent logs for debugging
                logs = self.agent_manager.get_agent_logs()
                logger.error(f"Agent logs:\n{logs}")
                
                return {
                    "success": False,
                    "agent_type": "code",
                    "error": error_msg,
                    "message": f"Failed to generate code: {error_msg}"
                }
        
        except Exception as e:
            logger.error(f"Code agent error: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "agent_type": "code",
                "error": str(e),
                "message": "Sorry, I encountered an error generating the code."
            }
    
    def stop_agent(self):
        """Stop the code execution agent container"""
        if self.agent_initialized:
            logger.info("🛑 Stopping AI agent container...")
            self.agent_manager.stop_agent_container()
            self.agent_initialized = False


# Singleton instance
_dual_agent_handler = None

def get_dual_agent_handler() -> DualAgentHandler:
    """Get singleton dual agent handler"""
    global _dual_agent_handler
    if _dual_agent_handler is None:
        _dual_agent_handler = DualAgentHandler()
    return _dual_agent_handler
