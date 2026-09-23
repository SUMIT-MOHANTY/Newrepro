"""
DSuite BRD Analyzer - Root Shim for LLM Logs
"""
import sys
from app.core.llm_logs import *
from app.core import llm_logs as _mod
sys.modules["llm_logs"] = _mod
