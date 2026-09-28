"""Resource limits — constants applied by process_manager and filesystem tools.

Architecture §7.2 resource_limits.py / §9.1:
Keep all limit constants in one place so they can be tuned via environment
variables without touching any other code.
"""
from __future__ import annotations

import os


class ResourceLimits:
    """Runtime resource limit constants, tunable via environment variables."""

    @property
    def MAX_BUILD_TIME_SECONDS(self) -> int:
        return int(os.environ.get("MAX_BUILD_TIME_SECONDS", "300"))

    @property
    def MAX_COMMAND_OUTPUT_BYTES(self) -> int:
        return int(os.environ.get("MAX_COMMAND_OUTPUT_BYTES", "1000000"))

    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        return int(os.environ.get("MAX_FILE_SIZE_BYTES", "5000000"))

    @property
    def MAX_FILES_IN_LISTING(self) -> int:
        return int(os.environ.get("MAX_FILES_IN_LISTING", "500"))

    @property
    def MAX_STEP_RETRIES(self) -> int:
        return int(os.environ.get("MAX_STEP_RETRIES", "2"))

    @property
    def MAX_BUILD_ATTEMPTS(self) -> int:
        return int(os.environ.get("MAX_BUILD_ATTEMPTS", "3"))

    @property
    def LLM_REQUEST_TIMEOUT_SECONDS(self) -> int:
        return int(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "120"))
