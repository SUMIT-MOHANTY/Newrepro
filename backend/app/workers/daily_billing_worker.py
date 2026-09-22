"""
Daily Billing Worker
Background worker responsible for triggering, scheduling, and configuring automated daily billing emails.
"""

import logging
from typing import Any, Dict, Optional
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    import daily_billing_email_service as raw_billing_worker
except ImportError:
    raw_billing_worker = None

logger = logging.getLogger(__name__)


class DailyBillingWorker:
    """
    Worker for orchestrating daily consumption digests, admin reports, and schedule parameters.
    """

    def __init__(self):
        self._worker = raw_billing_worker

    def get_controls(self) -> Dict[str, Any]:
        """Load email dispatch filters, recipient overrides, and schedule timing."""
        if not self._worker:
            return {}
        return self._worker.load_email_controls()

    def update_controls(self, controls: Dict[str, Any]) -> bool:
        """Persist modified email dispatch controls to email_controls.json."""
        if not self._worker:
            return False
        return self._worker.save_email_controls(controls)

    async def trigger_dispatch(self, db) -> Dict[str, Any]:
        """Execute an immediate daily billing email dispatch cycle."""
        if not self._worker:
            return {"status": "error", "message": "Daily billing service not available"}

        logger.info("[DailyBillingWorker] Manually triggering daily billing email run...")
        try:
            results = await self._worker.send_daily_billing_emails(db)
            return {
                "status": "success",
                "message": "Daily billing emails dispatched successfully",
                "results": results,
            }
        except Exception as e:
            logger.error(f"[DailyBillingWorker] Dispatch failed: {e}")
            return {"status": "error", "message": str(e)}


daily_billing_worker = DailyBillingWorker()
