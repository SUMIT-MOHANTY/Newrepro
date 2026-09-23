"""
DSuite BRD Analyzer - Root Shim for RSA Utils
"""
import sys
from app.core.rsa_utils import *
from app.core import rsa_utils as _mod
sys.modules["rsa_utils"] = _mod
