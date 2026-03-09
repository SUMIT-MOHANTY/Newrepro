"""
Backfill sub_type quota columns for existing organizations.

For any org where the total quota > 0 but sub_type quotas are still 0,
this script splits them as:  ~71% dev, ~29% test  (so 140 → 100 dev + 40 test).

You can override the ratio at the top of the file.
"""
import sys
sys.path.insert(0, '.')

from database import SessionLocal
import models

# ─── Config ───────────────────────────────────────────────────────────────────
DEV_RATIO = 100 / 140   # ≈ 0.714  →  e.g. 140 total → 100 dev, 40 test
# ──────────────────────────────────────────────────────────────────────────────

db = SessionLocal()

try:
    rows = db.query(models.OrganizationAgentQuota).all()
    if not rows:
        print("No quota rows found.")
    else:
        for q in rows:
            changed = False
            org = q.organization_name

            # ── Dedicated ──────────────────────────────────────────────────
            ded_total = int(q.dedicated_quota or 0)
            if ded_total > 0 and int(q.dedicated_dev_quota or 0) == 0 and int(q.dedicated_test_quota or 0) == 0:
                dev = round(ded_total * DEV_RATIO)
                test = ded_total - dev
                q.dedicated_dev_quota = dev
                q.dedicated_test_quota = test
                print(f"[{org}] Dedicated {ded_total} → dev={dev}, test={test}")
                changed = True

            # ── Shared ─────────────────────────────────────────────────────
            sh_total = int(q.shared_quota or 0)
            if sh_total > 0 and int(q.shared_dev_quota or 0) == 0 and int(q.shared_test_quota or 0) == 0:
                dev = round(sh_total * DEV_RATIO)
                test = sh_total - dev
                q.shared_dev_quota = dev
                q.shared_test_quota = test
                print(f"[{org}] Shared {sh_total} → dev={dev}, test={test}")
                changed = True

            if not changed:
                print(f"[{org}] Already has sub_type data — skipped.")

        db.commit()
        print("\nDone. Backfill committed.")
finally:
    db.close()
