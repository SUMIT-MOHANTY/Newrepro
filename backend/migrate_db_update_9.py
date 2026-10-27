"""
Migration: Add local-first state management tables
 
This migration adds four new tables that form the local-first state layer
for agent orchestration. These tables make the system independent of NXDune
for runtime decisions and survive server restarts.
 
Tables added:
  - agent_task_ownerships        : Canonical record of which agent owns which task
  - project_canonical_states     : Immutable bootstrap artifacts (tree, spec, stack)
  - agent_execution_checkpoints  : Per-agent progress snapshots for resume-after-restart
  - nxdune_sync_logs             : Audit trail of all NXDune sync attempts
"""
from sqlalchemy import text
from database import engine
 
 
def upgrade():
    """Create local-first state management tables"""
    with engine.connect() as conn:
 
        # ── Table 1: agent_task_ownerships ────────────────────────────────────
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_task_ownerships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL,
                    task_id VARCHAR NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    task_title VARCHAR,
                    task_data JSON,
                    task_lane VARCHAR,
                    status VARCHAR NOT NULL DEFAULT 'claimed',
                    claimed_at DATETIME,
                    started_at DATETIME,
                    completed_at DATETIME,
                    branch_name VARCHAR,
                    files_written JSON,
                    error_message TEXT,
                    nxdune_synced BOOLEAN DEFAULT 0,
                    nxdune_synced_at DATETIME,
                    nxdune_sync_attempts INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (project_token, task_id)
                )
            """))
            conn.commit()
            print("✓ Created agent_task_ownerships table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ agent_task_ownerships table already exists")
            else:
                raise
 
        # Indexes for agent_task_ownerships
        for idx_name, col in [
            ("ix_agent_task_ownerships_project_token", "project_token"),
            ("ix_agent_task_ownerships_task_id",       "task_id"),
            ("ix_agent_task_ownerships_agent_id",       "agent_id"),
            ("ix_agent_task_ownerships_status",         "status"),
            ("ix_agent_task_ownerships_claimed_at",     "claimed_at"),
            ("ix_agent_task_ownerships_created_at",     "created_at"),
        ]:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} "
                    f"ON agent_task_ownerships({col})"
                ))
                conn.commit()
                print(f"  ✓ Created index on agent_task_ownerships.{col}")
            except Exception as e:
                print(f"  ⚠ Error creating index {idx_name}: {e}")
 
        # ── Table 2: project_canonical_states ─────────────────────────────────
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS project_canonical_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL UNIQUE,
                    canonical_tree TEXT,
                    technical_spec TEXT,
                    tech_stack JSON,
                    bootstrap_branch VARCHAR,
                    domain_file_map JSON,
                    is_ready BOOLEAN DEFAULT 0,
                    force_reset BOOLEAN DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    last_agent_id VARCHAR,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✓ Created project_canonical_states table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ project_canonical_states table already exists")
            else:
                raise
 
        # Indexes for project_canonical_states
        for idx_name, col in [
            ("ix_project_canonical_states_project_token", "project_token"),
            ("ix_project_canonical_states_is_ready",      "is_ready"),
        ]:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} "
                    f"ON project_canonical_states({col})"
                ))
                conn.commit()
                print(f"  ✓ Created index on project_canonical_states.{col}")
            except Exception as e:
                print(f"  ⚠ Error creating index {idx_name}: {e}")
 
        # ── Table 3: agent_execution_checkpoints ──────────────────────────────
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_execution_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    current_task_id VARCHAR,
                    current_task_data JSON,
                    current_task_status VARCHAR,
                    progress INTEGER DEFAULT 0,
                    progress_message VARCHAR,
                    last_milestone VARCHAR,
                    files_written_so_far JSON,
                    version INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (project_token, agent_id)
                )
            """))
            conn.commit()
            print("✓ Created agent_execution_checkpoints table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ agent_execution_checkpoints table already exists")
            else:
                raise
 
        # Indexes for agent_execution_checkpoints
        for idx_name, col in [
            ("ix_agent_execution_checkpoints_project_token",  "project_token"),
            ("ix_agent_execution_checkpoints_agent_id",       "agent_id"),
            ("ix_agent_execution_checkpoints_current_task_id","current_task_id"),
        ]:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} "
                    f"ON agent_execution_checkpoints({col})"
                ))
                conn.commit()
                print(f"  ✓ Created index on agent_execution_checkpoints.{col}")
            except Exception as e:
                print(f"  ⚠ Error creating index {idx_name}: {e}")
 
        # ── Table 4: nxdune_sync_logs ─────────────────────────────────────────
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nxdune_sync_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL,
                    agent_id VARCHAR,
                    task_id VARCHAR,
                    operation VARCHAR NOT NULL,
                    payload JSON,
                    success BOOLEAN NOT NULL,
                    status_code INTEGER,
                    error_message TEXT,
                    response_body TEXT,
                    retry_count INTEGER DEFAULT 0,
                    last_retry_at DATETIME,
                    permanently_failed BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✓ Created nxdune_sync_logs table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ nxdune_sync_logs table already exists")
            else:
                raise
 
        # Indexes for nxdune_sync_logs
        for idx_name, col in [
            ("ix_nxdune_sync_logs_project_token",      "project_token"),
            ("ix_nxdune_sync_logs_agent_id",           "agent_id"),
            ("ix_nxdune_sync_logs_task_id",            "task_id"),
            ("ix_nxdune_sync_logs_success",            "success"),
            ("ix_nxdune_sync_logs_created_at",         "created_at"),
        ]:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} "
                    f"ON nxdune_sync_logs({col})"
                ))
                conn.commit()
                print(f"  ✓ Created index on nxdune_sync_logs.{col}")
            except Exception as e:
                print(f"  ⚠ Error creating index {idx_name}: {e}")
 
 
def downgrade():
    """Remove local-first state management tables (in dependency order)"""
    with engine.connect() as conn:
        for table in [
            "nxdune_sync_logs",
            "agent_execution_checkpoints",
            "project_canonical_states",
            "agent_task_ownerships",
        ]:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                conn.commit()
                print(f"✓ Removed {table} table")
            except Exception as e:
                print(f"⚠ Error removing {table}: {e}")
 
 
if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add local-first state management tables")
    print("=" * 60)
    print()
    print("This migration adds four tables for the local-first state layer:")
    print("  • agent_task_ownerships       - Canonical task ownership per agent")
    print("  • project_canonical_states    - Immutable bootstrap artifacts")
    print("  • agent_execution_checkpoints - Resume-after-restart snapshots")
    print("  • nxdune_sync_logs            - NXDune sync audit trail")
    print()
    print("Why this migration is needed:")
    print("  • Agents no longer depend solely on NXDune for runtime decisions")
    print("  • Task assignments survive server restarts (no more 'Skipping restore')")
    print("  • Bootstrap canonical tree/spec is immutable after first completion")
    print("  • NXDune failures are logged as an audit trail, not silently dropped")
    print()
 
    try:
        upgrade()
        print()
        print("=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Migration failed: {e}")
        print("=" * 60)
        raise
 
