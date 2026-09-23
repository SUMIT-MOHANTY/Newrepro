"""
DSuite BRD Analyzer - Root Shim for Prompt Logger
"""
import sys
from app.core.prompt_logger import *
from app.core import prompt_logger as _mod
sys.modules["prompt_logger"] = _mod
