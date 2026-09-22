import os
import sys
import time
import logging
import subprocess
import argparse
from typing import List, Set, Dict, Tuple, Optional

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text, create_engine
try:
    from database import engine as default_engine
except Exception:
    default_engine = None

logger = logging.getLogger("migrations")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_engine():
    """Get active database engine."""
    if default_engine is not None:
        return default_engine
    from database import SQLALCHEMY_DATABASE_URL
    return create_engine(SQLALCHEMY_DATABASE_URL)


def ensure_migrations_table(conn) -> None:
    """Create the schema_migrations tracking table if it does not already exist."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_name VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            execution_time_ms INTEGER DEFAULT 0
        )
    """))
    conn.commit()


def get_applied_migrations(conn) -> Dict[str, Dict]:
    """Retrieve all previously applied migrations from the database."""
    ensure_migrations_table(conn)
    result = conn.execute(text("SELECT migration_name, applied_at, execution_time_ms FROM schema_migrations"))
    applied = {}
    for row in result.fetchall():
        applied[row[0]] = {
            "applied_at": str(row[1]),
            "execution_time_ms": row[2] or 0
        }
    return applied


def record_migration(conn, migration_name: str, execution_time_ms: int = 0) -> None:
    """Record a newly applied migration into the tracking table."""
    conn.execute(
        text("INSERT OR REPLACE INTO schema_migrations (migration_name, applied_at, execution_time_ms) VALUES (:name, CURRENT_TIMESTAMP, :ms)"),
        {"name": migration_name, "ms": execution_time_ms}
    )
    conn.commit()


def get_migration_files() -> List[str]:
    """Discover all migration scripts in backend/migrations in execution order."""
    migrations_dir = os.path.join(BACKEND_DIR, "migrations")
    if not os.path.isdir(migrations_dir):
        return []

    migration_scripts = []
    has_init_db = False

    for file in os.listdir(migrations_dir):
        if file.endswith(".py") and file != "__init__.py":
            if file == "initialize_fresh_db.py":
                has_init_db = True
            else:
                migration_scripts.append(file)

    migration_scripts.sort()

    # Always prioritize initialize_fresh_db.py first if present
    if has_init_db:
        migration_scripts.insert(0, "initialize_fresh_db.py")

    return migration_scripts


def show_migration_status() -> None:
    """Print the applied vs pending status of all migration files."""
    engine = get_engine()
    migration_files = get_migration_files()

    with engine.connect() as conn:
        applied = get_applied_migrations(conn)

    print("=" * 75)
    print(f"{'Migration Script':<45} | {'Status':<10} | {'Applied At':<18}")
    print("=" * 75)

    pending_count = 0
    applied_count = 0

    for script in migration_files:
        if script in applied:
            applied_count += 1
            info = applied[script]
            applied_at = info["applied_at"][:19] if info["applied_at"] else "Unknown"
            print(f"{script:<45} | \033[92mAPPLIED\033[0m    | {applied_at}")
        else:
            pending_count += 1
            print(f"{script:<45} | \033[93mPENDING\033[0m    | -")

    print("=" * 75)
    print(f"Total: {len(migration_files)} | Applied: {applied_count} | Pending: {pending_count}")
    print("=" * 75)


def run_migrations(
    force: bool = False,
    fake: bool = False,
    verbose: bool = True
) -> Tuple[int, int]:
    """
    Run pending migrations and record each successful execution in schema_migrations.
    
    Returns:
        (success_count, failure_count)
    """
    engine = get_engine()
    migrations_dir = os.path.join(BACKEND_DIR, "migrations")
    all_scripts = get_migration_files()

    with engine.connect() as conn:
        applied_map = get_applied_migrations(conn)

    if force:
        pending_scripts = all_scripts
    else:
        pending_scripts = [s for s in all_scripts if s not in applied_map]

    if not pending_scripts:
        if verbose:
            logger.info(f"[Migrations] Database schema is up to date ({len(applied_map)} migrations applied).")
        return (0, 0)

    if verbose:
        logger.info(f"[Migrations] Found {len(pending_scripts)} pending migration(s) to execute.")

    # If --fake is requested, simply mark them as applied without running
    if fake:
        with engine.connect() as conn:
            for script in pending_scripts:
                record_migration(conn, script, execution_time_ms=0)
                if verbose:
                    logger.info(f"[Migrations] [FAKE] Marked {script} as applied.")
        return (len(pending_scripts), 0)

    success_count = 0
    failure_count = 0

    env = os.environ.copy()
    env["PYTHONPATH"] = BACKEND_DIR + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"

    for idx, script in enumerate(pending_scripts, 1):
        script_path = os.path.join(migrations_dir, script)
        if verbose:
            logger.info(f"[{idx}/{len(pending_scripts)}] Running migration: {script}...")

        start_time = time.time()
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            if result.returncode == 0:
                with engine.connect() as conn:
                    record_migration(conn, script, execution_time_ms=elapsed_ms)

                success_count += 1
                if verbose:
                    logger.info(f"[Migrations] ✓ SUCCESS: {script} ({elapsed_ms}ms)")
                    stdout_clean = (result.stdout or "").strip()
                    if stdout_clean:
                        for line in stdout_clean.split("\n"):
                            logger.info(f"    {line}")
            else:
                failure_count += 1
                logger.error(f"[Migrations] ✗ FAILED: {script} (Exit Code: {result.returncode})")
                if result.stdout and result.stdout.strip():
                    logger.error(f"--- stdout ---\n{result.stdout.strip()}")
                if result.stderr and result.stderr.strip():
                    logger.error(f"--- stderr ---\n{result.stderr.strip()}")
                
                # Stop on first migration error so downstream scripts don't corrupt state
                logger.error(f"[Migrations] Halting further migrations due to failure in {script}.")
                break

        except Exception as ex:
            failure_count += 1
            logger.error(f"[Migrations] ✗ Unexpected error executing {script}: {ex}")
            break

    if verbose:
        logger.info(f"[Migrations] Finished: {success_count} applied, {failure_count} failed out of {len(pending_scripts)} pending.")

    return (success_count, failure_count)


def main():
    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument("--status", action="store_true", help="Show applied vs pending migrations without running")
    parser.add_argument("--fake", action="store_true", help="Mark pending migrations as applied without executing them")
    parser.add_argument("--force", action="store_true", help="Force re-run all migrations even if already recorded")
    parser.add_argument("--quiet", action="store_true", help="Suppress detailed logs")
    args = parser.parse_args()

    if args.status:
        show_migration_status()
        sys.exit(0)

    success_cnt, fail_cnt = run_migrations(
        force=args.force,
        fake=args.fake,
        verbose=not args.quiet
    )

    if fail_cnt > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
