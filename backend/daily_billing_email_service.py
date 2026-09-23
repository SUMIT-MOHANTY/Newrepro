"""
DSuite BRD Analyzer - Root Shim for Daily Billing Email Service
Maintains backward compatibility for legacy imports (import daily_billing_email_service).
"""
import sys
from app.workers.daily_billing_email_service import *
from app.workers import daily_billing_email_service as _worker_module

sys.modules["daily_billing_email_service"] = _worker_module
