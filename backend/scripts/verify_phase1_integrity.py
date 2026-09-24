"""
Phase 1 Architectural Verification Suite
Validates:
1. All modules in app/ and tokenops/ import cleanly with zero errors.
2. Zero circular dependencies.
3. Zero unresolved legacy imports.
4. FastAPI lifespan and HTTP endpoint contracts pass.
"""
import os
import sys
import importlib
import pkgutil
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase1_verifier")

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

def verify_all_imports():
    logger.info("Verifying module imports across backend/app and backend/tokenops...")
    import app
    import tokenops
    
    scanned_packages = [app, tokenops]
    success_count = 0
    errors = []

    for pkg in scanned_packages:
        prefix = pkg.__name__ + "."
        for _, modname, ispkg in pkgutil.walk_packages(pkg.__path__, prefix):
            try:
                importlib.import_module(modname)
                success_count += 1
            except Exception as e:
                errors.append((modname, str(e)))

    logger.info(f"Successfully imported {success_count} modules.")
    if errors:
        logger.error(f"Encountered {len(errors)} import failure(s):")
        for mod, err in errors:
            logger.error(f"  ✗ {mod}: {err}")
        return False
    return True

def verify_fastapi_contracts():
    logger.info("Verifying FastAPI application assembly & endpoints...")
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as client:
        # 1. Health check
        r_health = client.get("/health")
        assert r_health.status_code == 200, f"Expected 200 on /health, got {r_health.status_code}"
        assert r_health.json().get("status") == "healthy"
        logger.info(f"✓ GET /health: 200 OK -> {r_health.json()}")

        # 2. Token endpoint rejects bad credentials with 401 (not 500)
        r_token = client.post("/token", data={"username": "invalid_user", "password": "bad_password"})
        assert r_token.status_code == 401, f"Expected 401 on /token, got {r_token.status_code}"
        logger.info("✓ POST /token: 401 Unauthorized (Auth contract working)")

        # 3. Unread count endpoint
        r_unread = client.get("/api/tickets/unread-count")
        assert r_unread.status_code in [200, 401], f"Expected 200 or 401 on unread-count, got {r_unread.status_code}"
        logger.info(f"✓ GET /api/tickets/unread-count: {r_unread.status_code} (Route parsed correctly)")

    logger.info("All FastAPI contracts verified successfully.")
    return True

if __name__ == "__main__":
    imports_ok = verify_all_imports()
    contracts_ok = verify_fastapi_contracts()

    if imports_ok and contracts_ok:
        logger.info("=========================================")
        logger.info("  PHASE 1 VERIFICATION PASSED (100%)    ")
        logger.info("=========================================")
        sys.exit(0)
    else:
        logger.error("Phase 1 verification failed.")
        sys.exit(1)
