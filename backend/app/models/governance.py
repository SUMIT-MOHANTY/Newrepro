import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import models

GovernanceResponse = getattr(models, "GovernanceResponse", None)
GovernanceQuestion = getattr(models, "GovernanceQuestion", None)
GovernanceQuestionOption = getattr(models, "GovernanceQuestionOption", None)
ProjectTag = getattr(models, "ProjectTag", None)

__all__ = [
    "GovernanceResponse",
    "GovernanceQuestion",
    "GovernanceQuestionOption",
    "ProjectTag",
]
