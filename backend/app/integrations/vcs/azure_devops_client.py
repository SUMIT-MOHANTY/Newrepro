import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import azure_devops_service
import azure_devops_oauth_service

__all__ = ["azure_devops_service", "azure_devops_oauth_service"]
