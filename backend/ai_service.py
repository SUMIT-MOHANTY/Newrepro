"""Root shim for AI service (BRD analysis)."""
import sys
from app.services.ai.ai_service import *
from app.services.ai import ai_service as _mod

sys.modules["ai_service"] = _mod
