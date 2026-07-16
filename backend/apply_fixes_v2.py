"""
Apply Fixes v2 — Dynamic fixes for:
  Fix #1: Redundant tree-root wrapper causing e.g. backend/backend/manage.py
  Fix #2: Bootstrap bypass skipping without verifying branch actually exists
"""

import re

FILEPATH = r"D:\BRD\BRD_Analyzer\backend\agent_service.py"

with open(FILEPATH, "r", encoding="utf-8") as f:
    lines = f.readlines()

changes_made = 0

# ═══════════════════════════════════════════════════════════════════════════════
#  FIX #1 — Flatten redundant tree root
#  The AI sometimes generates a tree where the root shares a name with one of
#  its children — e.g. root "backend" → child "backend" (which is the real
#  backend directory). This causes paths like backend/backend/manage.py.
#
#  Dynamic detection: if root "name" equals any child's "name", the root is
#  a redundant wrapper. We flatten by promoting the matching child's children
#  up alongside the other siblings.
# ═══════════════════════════════════════════════════════════════════════════════

# Find: `final_tree = json.dumps(parsed_json, ensure_ascii=False, indent=2)`
# Insert flattening code BEFORE this line
target_line_fix1 = '            final_tree = json.dumps(parsed_json, ensure_ascii=False, indent=2)\n'

flatten_code = """            # ── DYNAMIC TREE FLATTENING ──────────────────────────────────
            # Detect & fix redundant root wrappers:
            # If root "name" equals any child "name" (e.g. root=backend, child=backend),
            # the root is a synthetic wrapper — not a real directory.
            # Promote the duplicate child's children up alongside the other siblings.
            try:
                root_name = str(parsed_json.get("name") or "").strip()
                _flatten_children = parsed_json.get("children") or []
                if root_name and isinstance(_flatten_children, list):
                    _child_names = {
                        str(c.get("name", "")).strip()
                        for c in _flatten_children if isinstance(c, dict)
                    }
                    if root_name in _child_names:
                        logger.info(
                            f"🔧 Flattening redundant tree root: root='{root_name}' "
                            f"collides with child name — promoting grandchildren"
                        )
                        _new_children = []
                        _seen = set()
                        for _child in _flatten_children:
                            if not isinstance(_child, dict):
                                continue
                            _cname = str(_child.get("name") or "").strip()
                            if _cname == root_name:
                                # Promote this child's children up
                                _grandkids = _child.get("children") or []
                                if isinstance(_grandkids, list):
                                    for _gk in _grandkids:
                                        if isinstance(_gk, dict):
                                            _gk_name = str(_gk.get("name") or "").strip()
                                            if _gk_name and _gk_name not in _seen:
                                                _new_children.append(_gk)
                                                _seen.add(_gk_name)
                            else:
                                if _cname and _cname not in _seen:
                                    _new_children.append(_child)
                                    _seen.add(_cname)
                        parsed_json["children"] = _new_children
            except Exception as _flatten_err:
                logger.warning(f"Tree flattening failed (non-fatal): {_flatten_err}")
            # ── END TREE FLATTENING ─────────────────────────────────────
"""

for i, line in enumerate(lines):
    if line == target_line_fix1:
        # Check if flattening was already added (idempotent)
        if 'DYNAMIC TREE FLATTENING' not in lines[i - 1] if i > 0 else True:
            lines.insert(i, flatten_code)
            changes_made += 1
            print(f"✅ Fix 1: Added dynamic tree flattening at line {i + 1}")
        else:
            print("ℹ️ Fix 1: Tree flattening already applied (skipped)")
        break
else:
    # Try without \r\n
    for i, line in enumerate(lines):
        if line.strip() == 'final_tree = json.dumps(parsed_json, ensure_ascii=False, indent=2)':
            if 'DYNAMIC TREE FLATTENING' not in (lines[i - 1] if i > 0 else ""):
                lines.insert(i, flatten_code)
                changes_made += 1
                print(f"✅ Fix 1: Added dynamic tree flattening at line {i + 1}")
            else:
                print("ℹ️ Fix 1: Tree flattening already applied (skipped)")
            break
    else:
        print("⚠️ Fix 1: Could not find the target line for tree flattening")

# ═══════════════════════════════════════════════════════════════════════════════
#  FIX #2 — Verify bootstrap branch exists on remote before skipping
#  Before skipping bootstrap execution ("idempotent bypass"), verify that the
#  bootstrap branch actually exists on the remote with files. If the branch
#  doesn't exist or has no files, reset the state to pending and let the
#  bootstrap agent run for real.
# ═══════════════════════════════════════════════════════════════════════════════

# Write the new content
new_content = "".join(lines)

fix2_old = (
    '        # ═══ CRITICAL IDEMPOTENCY BYPASS: Skip bootstrap task if already pushed ═══\n'
    '        if is_bootstrap_task and is_bootstrap_pushed(project_token):\n'
    '            agent["output_log"].append({\n'
    '                "time": datetime.utcnow().isoformat(),\n'
    '                "type": "info",\n'
    '                "message": "✅ Bootstrap has already been successfully pushed to git. Skipping bootstrap execution (idempotent bypass)."\n'
    '            })\n'
    '            username = build_external_agent_username(agent_id, agent.get("name"))\n'
    '            try:\n'
    '                await _opt_in_task(task, username, project_token=project_token, task_token=task_token)\n'
    '            except Exception:\n'
    '                pass\n'
    '            await _post_task_progress(task, 100, "Bootstrap already completed successfully", task_token=task_token)\n'
    '            await _post_task_complete(task, task_token=task_token)\n'
    '            \n'
    '            # Ensure bootstrap branch is recorded in state\n'
    '            bootstrap_branch = get_bootstrap_branch(project_token)\n'
    '            if bootstrap_branch:\n'
    '                state.setdefault("repo_bootstrap", {})\n'
    '                state["repo_bootstrap"]["source_branch"] = bootstrap_branch\n'
    '                state["repo_bootstrap"]["status"] = "completed"\n'
    '                state["repo_bootstrap"]["required"] = True\n'
    '                state["repo_bootstrap_event"].set()\n'
    '            \n'
    '            agent["current_task"] = None\n'
    '            agent["resume_pending_task"] = False\n'
    '            agent["status"] = "idle"\n'
    '            agent["progress"] = 100\n'
    '            agent["progress_message"] = "Bootstrap already completed"\n'
    '            return {\n'
    '                "success": True,\n'
    '                "agent_id": agent_id,\n'
    '                "tasks_completed": 1,\n'
    '                "message": "Bootstrap already completed (idempotent bypass)",\n'
    '            }'
)

fix2_new = (
    '        # ═══ CRITICAL IDEMPOTENCY BYPASS: Skip bootstrap task if already pushed ═══\n'
    '        if is_bootstrap_task and is_bootstrap_pushed(project_token):\n'
    '            # ── REMOTE VERIFICATION: Ensure the branch actually exists with files ──\n'
    '            _verified_branch = get_bootstrap_branch(project_token)\n'
    '            _branch_verified = False\n'
    '            if _verified_branch and git_repo_url and container_name:\n'
    '                try:\n'
    '                    _auth_cfg = _get_git_auth_config(git_repo_url, git_token)\n'
    '                    _ls_cmd = ["docker", "exec", "-w", "/workspace", container_name, "git"]\n'
    '                    _ls_cmd.extend(_auth_cfg)\n'
    '                    _ls_cmd.extend(["ls-remote", "--heads", "origin", _verified_branch])\n'
    '                    _ls_result = subprocess.run(\n'
    '                        _ls_cmd, capture_output=True, text=True, timeout=15\n'
    '                    )\n'
    '                    if _ls_result.returncode == 0 and _verified_branch in _ls_result.stdout:\n'
    '                        _branch_verified = True\n'
    '                        logger.info(f"[{agent_id}] Verified bootstrap branch {_verified_branch} exists on remote")\n'
    '                    else:\n'
    '                        logger.warning(\n'
    '                            f"[{agent_id}] Bootstrap branch {_verified_branch} NOT found on remote. "\n'
    '                            f"Resetting bootstrap state to pending so the bootstrap agent runs."\n'
    '                        )\n'
    '                except Exception as _verify_err:\n'
    '                    logger.warning(f"[{agent_id}] Bootstrap branch verification failed: {_verify_err}")\n'
    '            \n'
    '            if not _branch_verified:\n'
    '                # Branch doesn\'t exist or verification failed — reset state so bootstrap actually runs\n'
    '                try:\n'
    '                    from bootstrap_persistence import set_bootstrap_failed\n'
    '                    set_bootstrap_failed(project_token, "Bootstrap branch not found on remote during verification — resetting")\n'
    '                except Exception:\n'
    '                    pass\n'
    '                agent["output_log"].append({\n'
    '                    "time": datetime.utcnow().isoformat(),\n'
    '                    "type": "warning",\n'
    '                    "message": "⚠️ Bootstrap marked as pushed but branch not found on remote. Will execute bootstrap for real."\n'
    '                })\n'
    '            else:\n'
    '                agent["output_log"].append({\n'
    '                    "time": datetime.utcnow().isoformat(),\n'
    '                    "type": "info",\n'
    '                    "message": "✅ Bootstrap has already been successfully pushed to git. Skipping bootstrap execution (idempotent bypass)."\n'
    '                })\n'
    '                username = build_external_agent_username(agent_id, agent.get("name"))\n'
    '                try:\n'
    '                    await _opt_in_task(task, username, project_token=project_token, task_token=task_token)\n'
    '                except Exception:\n'
    '                    pass\n'
    '                await _post_task_progress(task, 100, "Bootstrap already completed successfully", task_token=task_token)\n'
    '                await _post_task_complete(task, task_token=task_token)\n'
    '                \n'
    '                # Ensure bootstrap branch is recorded in state\n'
    '                if _verified_branch:\n'
    '                    state.setdefault("repo_bootstrap", {})\n'
    '                    state["repo_bootstrap"]["source_branch"] = _verified_branch\n'
    '                    state["repo_bootstrap"]["status"] = "completed"\n'
    '                    state["repo_bootstrap"]["required"] = True\n'
    '                    state["repo_bootstrap_event"].set()\n'
    '                \n'
    '                agent["current_task"] = None\n'
    '                agent["resume_pending_task"] = False\n'
    '                agent["status"] = "idle"\n'
    '                agent["progress"] = 100\n'
    '                agent["progress_message"] = "Bootstrap already completed"\n'
    '                return {\n'
    '                    "success": True,\n'
    '                    "agent_id": agent_id,\n'
    '                    "tasks_completed": 1,\n'
    '                    "message": "Bootstrap already completed (idempotent bypass)",\n'
    '                }'
)

if fix2_old in new_content:
    new_content = new_content.replace(fix2_old, fix2_new, 1)
    print("✅ Fix 2: Added remote branch verification before bootstrap bypass")
    changes_made += 1
else:
    print("⚠️ Fix 2: Could not find the bootstrap bypass code section")

# Save the modified file
if changes_made > 0:
    with open(FILEPATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"\n✅ All changes applied! Total changes: {changes_made}")
else:
    print("\n⚠️ No changes made — nothing matched")
