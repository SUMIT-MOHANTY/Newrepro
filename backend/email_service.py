"""
DSuite BRD Analyzer - Root Shim for Email Service
Maintains backward compatibility for legacy imports (import email_service).
"""
import sys
from app.services.email_service import *
from app.services import email_service as _svc_module

# Ensure module is accessible as module reference
sys.modules["email_service"] = _svc_module
