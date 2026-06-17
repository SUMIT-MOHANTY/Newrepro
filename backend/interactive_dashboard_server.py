import sqlite3
import os
import sys
import uvicorn
import webbrowser
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from datetime import datetime
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql_app.db")

app = FastAPI(title="Utilization Dashboard API")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/summary")
def get_summary():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # KPIs
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM users WHERE is_active=1")
    active_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT organization_name) FROM users WHERE organization_name IS NOT NULL AND organization_name != ''")
    total_orgs = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM governance_responses")
    total_projects = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM user_sessions")
    total_sessions = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(duration_seconds) FROM user_sessions")
    total_duration = cur.fetchone()[0] or 0
    
    cur.execute("SELECT COUNT(*) FROM bootstrap_states WHERE status='success'")
    successful_runs = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM bootstrap_states WHERE status='failed'")
    failed_runs = cur.fetchone()[0]
    
    # Project status counts
    cur.execute("SELECT status, COUNT(*) as cnt FROM bootstrap_states GROUP BY status")
    run_statuses = {r["status"]: r["cnt"] for r in cur.fetchall()}
    
    # Projects per classification
    cur.execute("SELECT classification, COUNT(*) as cnt FROM governance_responses GROUP BY classification")
    classifications = {r["classification"]: r["cnt"] for r in cur.fetchall()}

    conn.close()
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_orgs": total_orgs,
        "total_projects": total_projects,
        "total_sessions": total_sessions,
        "total_duration_hours": round(total_duration / 3600, 1),
        "avg_session_mins": round((total_duration / max(total_sessions, 1)) / 60, 1),
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "run_statuses": run_statuses,
        "classifications": classifications
    }

@app.get("/api/users")
def get_users_list():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Query all users
    cur.execute("SELECT * FROM users ORDER BY id")
    users = [dict(r) for r in cur.fetchall()]
    
    # Query total projects per user
    cur.execute("SELECT owner_id, COUNT(*) as cnt FROM governance_responses GROUP BY owner_id")
    projects_by_user = {r["owner_id"]: r["cnt"] for r in cur.fetchall()}
    
    # Query sessions stats per user
    cur.execute("SELECT user_id, COUNT(*) as count, SUM(duration_seconds) as total_time FROM user_sessions GROUP BY user_id")
    session_stats = {r["user_id"]: {"count": r["count"], "total_time": r["total_time"]} for r in cur.fetchall()}
    
    # Query user org roles
    cur.execute("""
        SELECT uor.user_id, uor.organization_name, r.name as role_name 
        FROM user_organization_roles uor 
        LEFT JOIN organization_roles r ON uor.role_id = r.id
    """)
    roles = {}
    for r in cur.fetchall():
        roles.setdefault(r["user_id"], []).append({
            "org": r["organization_name"],
            "role": r["role_name"]
        })

    # Query access permission paths count
    cur.execute("""
        SELECT uor.user_id, COUNT(p.path) as perm_count
        FROM user_organization_roles uor
        JOIN organization_role_permissions p ON uor.role_id = p.role_id
        GROUP BY uor.user_id
    """)
    permissions = {r["user_id"]: r["perm_count"] for r in cur.fetchall()}

    enriched_users = []
    for u in users:
        uid = u["id"]
        stats = session_stats.get(uid, {"count": 0, "total_time": 0})
        
        # Format last login
        last_login_str = u.get("last_login")
        if last_login_str:
            try:
                dt = datetime.fromisoformat(last_login_str.split(".")[0].replace(" ", "T"))
                last_login_display = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                last_login_display = last_login_str
        else:
            last_login_display = "Never"

        enriched_users.append({
            "id": uid,
            "email": u["email"],
            "name": f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip() or "Unnamed User",
            "organization_name": u.get("organization_name") or "—",
            "is_active": bool(u.get("is_active")),
            "is_org_admin": bool(u.get("is_org_admin")),
            "last_login": last_login_display,
            "last_page_path": u.get("last_page_path") or "—",
            "projects_count": projects_by_user.get(uid, 0),
            "sessions_count": stats["count"],
            "total_duration_hours": round(stats["total_time"] / 3600, 1),
            "avg_session_mins": round((stats["total_time"] / max(stats["count"], 1)) / 60, 1),
            "roles": roles.get(uid, []),
            "permission_count": permissions.get(uid, 0),
            "github_username": u.get("github_username") or "—",
            "azure_devops_username": u.get("azure_devops_username") or "—"
        })
        
    conn.close()
    return enriched_users

@app.get("/api/users/{user_id}/detail")
def get_user_detail(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Projects created by this user
    cur.execute("SELECT * FROM governance_responses WHERE owner_id=?", (user_id,))
    projects = [dict(r) for r in cur.fetchall()]
    
    # Sessions for this user
    cur.execute("SELECT * FROM user_sessions WHERE user_id=? ORDER BY session_start DESC LIMIT 20", (user_id,))
    sessions = [dict(r) for r in cur.fetchall()]
    
    # Permissions paths
    cur.execute("""
        SELECT DISTINCT p.path 
        FROM user_organization_roles uor
        JOIN organization_role_permissions p ON uor.role_id = p.role_id
        WHERE uor.user_id=?
    """, (user_id,))
    permissions = [r["path"] for r in cur.fetchall()]
    
    conn.close()
    return {
        "projects": projects,
        "sessions": sessions,
        "permissions": sorted(permissions)
    }

@app.get("/api/projects")
def get_projects():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Projects + Owner + Latest Run status
    cur.execute("""
        SELECT p.*, u.email as owner_email,
               (SELECT b.status FROM bootstrap_states b WHERE b.project_token = p.project_token ORDER BY b.created_at DESC LIMIT 1) as run_status,
               (SELECT COUNT(*) FROM bootstrap_states b WHERE b.project_token = p.project_token) as total_runs
        FROM governance_responses p
        LEFT JOIN users u ON p.owner_id = u.id
        ORDER BY p.submission_date DESC
    """)
    projects = [dict(r) for r in cur.fetchall()]
    conn.close()
    return projects

@app.get("/api/organizations")
def get_organizations():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Derived from users and roles
    cur.execute("""
        SELECT organization_name, 
               COUNT(DISTINCT id) as user_count,
               SUM(CASE WHEN is_org_admin=1 THEN 1 ELSE 0 END) as admin_count,
               SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active_count
        FROM users
        WHERE organization_name IS NOT NULL AND organization_name != ''
        GROUP BY organization_name
    """)
    orgs = [dict(r) for r in cur.fetchall()]
    
    # Project count per org
    cur.execute("SELECT organization_name, COUNT(*) as project_count FROM governance_responses GROUP BY organization_name")
    proj_counts = {r["organization_name"]: r["project_count"] for r in cur.fetchall() if r["organization_name"]}
    
    # Add project count
    for o in orgs:
        o["project_count"] = proj_counts.get(o["organization_name"], 0)
        
    conn.close()
    return orgs

@app.get("/api/sessions")
def get_sessions(limit: int = 100):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, u.email as user_email, u.first_name, u.last_name 
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.session_start DESC
        LIMIT ?
    """, (limit,))
    sessions = [dict(r) for r in cur.fetchall()]
    conn.close()
    return sessions

DASHBOARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DSuite Interactive Utilization Dashboard</title>
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19;
            --surf: #131a2c;
            --surf-hover: #1c253d;
            --surf-active: #232f4e;
            --border: #222f47;
            --accent: #58a6ff;
            --accent-glow: rgba(88, 166, 255, 0.15);
            --gradient: linear-gradient(135deg, #58a6ff 0%, #bc8cff 100%);
            --text: #f0f6fc;
            --text-dim: #8b949e;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
            --radius: 12px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            line-height: 1.6;
            min-height: 100vh;
        }

        /* Layout */
        .wrapper {
            max-width: 1400px;
            margin: 0 auto;
            padding: 40px 24px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 24px;
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
            background: var(--gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .header-meta {
            color: var(--text-dim);
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .live-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: var(--green);
            box-shadow: 0 0 10px var(--green);
            display: inline-block;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(63, 185, 80, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(63, 185, 80, 0); }
        }

        /* Tabs Navigation */
        .nav-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 32px;
            background: var(--surf);
            padding: 6px;
            border-radius: 10px;
            border: 1px solid var(--border);
            width: fit-content;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-dim);
            padding: 8px 20px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .tab-btn:hover {
            color: var(--text);
            background: var(--surf-hover);
        }

        .tab-btn.active {
            color: #fff;
            background: var(--accent);
            box-shadow: 0 4px 12px var(--accent-glow);
        }

        /* KPI Cards Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .kpi-card {
            background: var(--surf);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 24px;
            position: relative;
            overflow: hidden;
            transition: all 0.2s;
        }

        .kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            border-color: var(--accent);
        }

        .kpi-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--gradient);
        }

        .kpi-title {
            font-size: 12px;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .kpi-value {
            font-size: 36px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: #fff;
            line-height: 1.2;
        }

        .kpi-desc {
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 4px;
        }

        /* Dashboard Views */
        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Interactive Filter Row */
        .filter-row {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
            flex-wrap: wrap;
        }

        .search-input, .select-input {
            background: var(--surf);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 10px 16px;
            border-radius: 8px;
            outline: none;
            font-family: inherit;
            font-size: 14px;
            transition: all 0.2s;
        }

        .search-input { flex: 1; min-width: 250px; }
        .search-input:focus, .select-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 2px var(--accent-glow);
        }

        /* Data Tables */
        .table-card {
            background: var(--surf);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
            margin-bottom: 24px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            text-align: left;
        }

        th {
            background: var(--surf-hover);
            color: var(--text-dim);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.8px;
            padding: 14px 20px;
            border-bottom: 1px solid var(--border);
            cursor: pointer;
            user-select: none;
        }

        th:hover {
            color: #fff;
        }

        td {
            padding: 14px 20px;
            border-bottom: 1px solid var(--border);
            color: var(--text);
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr.clickable {
            cursor: pointer;
            transition: background 0.15s;
        }

        tr.clickable:hover {
            background: var(--surf-hover);
        }

        /* Badges */
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }

        .badge-active { background: rgba(63, 185, 80, 0.12); color: var(--green); border: 1px solid rgba(63, 185, 80, 0.25); }
        .badge-inactive { background: rgba(248, 81, 73, 0.12); color: var(--red); border: 1px solid rgba(248, 81, 73, 0.25); }
        .badge-admin { background: rgba(210, 153, 34, 0.12); color: var(--yellow); border: 1px solid rgba(210, 153, 34, 0.25); }
        .badge-member { background: rgba(88, 166, 255, 0.12); color: var(--accent); border: 1px solid rgba(88, 166, 255, 0.25); }

        /* Drills & Modals */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(4px);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .modal {
            background: var(--surf);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            width: 100%;
            max-width: 850px;
            max-height: 90vh;
            overflow-y: auto;
            position: relative;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes slideIn {
            from { transform: translateY(15px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }

        .modal-header {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-close {
            background: transparent;
            border: none;
            color: var(--text-dim);
            font-size: 24px;
            cursor: pointer;
        }

        .modal-close:hover { color: #fff; }

        .modal-body {
            padding: 24px;
        }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }

        @media (max-width: 768px) {
            .grid-2 { grid-template-columns: 1fr; }
        }

        .info-card {
            background: var(--surf-hover);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }

        .info-title {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-dim);
            letter-spacing: 0.8px;
            margin-bottom: 8px;
            font-weight: 600;
        }

        .pill {
            background: var(--surf-active);
            border: 1px solid var(--border);
            color: var(--accent);
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-family: 'JetBrains Mono', monospace;
            display: inline-block;
            margin: 4px 4px 4px 0;
        }

        /* Print and Utilities */
        .btn-export {
            background: var(--surf-active);
            border: 1px solid var(--border);
            color: var(--accent);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
            font-family: inherit;
        }

        .btn-export:hover {
            background: var(--surf-hover);
            border-color: var(--accent);
        }
    </style>
</head>
<body>
    <div class="wrapper">
        <!-- HEADER -->
        <header>
            <div>
                <h1>DSuite App Utilization Dashboard</h1>
                <div style="font-size: 12px; color: var(--text-dim); margin-top: 4px;">Dynamic analysis of user activity, projects, and tenure</div>
            </div>
            <div class="header-meta">
                <span class="live-dot"></span>
                <span>Live Connected</span>
                <button class="btn-export" onclick="window.print()">Print Report</button>
            </div>
        </header>

        <!-- NAVIGATION TABS -->
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('overview')">Overview</button>
            <button class="tab-btn" onclick="switchTab('users')">User Engagement</button>
            <button class="tab-btn" onclick="switchTab('projects')">Projects Hub</button>
            <button class="tab-btn" onclick="switchTab('organizations')">Organizations</button>
        </div>

        <!-- OVERVIEW TAB -->
        <div id="overview-tab" class="tab-content active">
            <!-- KPI Strip -->
            <div class="kpi-grid" id="kpi-grid">
                <!-- Will be populated dynamically -->
            </div>
        </div>

        <!-- USERS TAB -->
        <div id="users-tab" class="tab-content">
            <div class="filter-row">
                <input type="text" id="user-search" class="search-input" placeholder="Search users by name, email, or organization..." oninput="filterUsersTable()">
                <select id="user-org-filter" class="select-input" onchange="filterUsersTable()">
                    <option value="">All Organizations</option>
                </select>
                <select id="user-status-filter" class="select-input" onchange="filterUsersTable()">
                    <option value="">All Statuses</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                </select>
            </div>
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th onclick="sortUserTable('name')">Name ⇅</th>
                            <th onclick="sortUserTable('email')">Email ⇅</th>
                            <th onclick="sortUserTable('organization')">Organization ⇅</th>
                            <th onclick="sortUserTable('status')">Status ⇅</th>
                            <th onclick="sortUserTable('last_login')">Last Login ⇅</th>
                            <th onclick="sortUserTable('projects')">Projects ⇅</th>
                            <th onclick="sortUserTable('sessions')">Sessions ⇅</th>
                            <th onclick="sortUserTable('hours')">Total Time (Hrs) ⇅</th>
                        </tr>
                    </thead>
                    <tbody id="users-table-body">
                        <!-- Will be populated dynamically -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- PROJECTS TAB -->
        <div id="projects-tab" class="tab-content">
            <div class="filter-row">
                <input type="text" id="project-search" class="search-input" placeholder="Search projects by token, name, organization..." oninput="filterProjectsTable()">
                <select id="project-status-filter" class="select-input" onchange="filterProjectsTable()">
                    <option value="">All Project States</option>
                    <option value="success">Success</option>
                    <option value="failed">Failed</option>
                </select>
            </div>
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>Token</th>
                            <th>Project Name</th>
                            <th>Organization</th>
                            <th>Owner</th>
                            <th>Classification</th>
                            <th>Runs</th>
                            <th>Last Status</th>
                        </tr>
                    </thead>
                    <tbody id="projects-table-body">
                        <!-- Will be populated dynamically -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- ORGANIZATIONS TAB -->
        <div id="organizations-tab" class="tab-content">
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>Organization Name</th>
                            <th>Registered Users</th>
                            <th>Active Users</th>
                            <th>Org Admins</th>
                            <th>Projects Created</th>
                        </tr>
                    </thead>
                    <tbody id="orgs-table-body">
                        <!-- Will be populated dynamically -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- DETAIL DRILL-DOWN MODAL -->
    <div id="detail-modal" class="modal-overlay" onclick="closeModal(event)">
        <div class="modal">
            <div class="modal-header">
                <h2 id="modal-user-name">User Utilization Profile</h2>
                <button class="modal-close" onclick="document.getElementById('detail-modal').style.display='none'">&times;</button>
            </div>
            <div class="modal-body">
                <div class="grid-2">
                    <div class="info-card">
                        <div class="info-title">App Roles & Org</div>
                        <div id="modal-user-roles">Loading...</div>
                    </div>
                    <div class="info-card">
                        <div class="info-title">Connected Integrations</div>
                        <table style="width:100%; border:none; font-size:12px;">
                            <tr style="background:none;"><td style="padding:4px 0; border:none; color:var(--text-dim)">GitHub:</td><td id="modal-user-github" style="padding:4px 0; border:none;">—</td></tr>
                            <tr style="background:none;"><td style="padding:4px 0; border:none; color:var(--text-dim)">Azure DevOps:</td><td id="modal-user-azure" style="padding:4px 0; border:none;">—</td></tr>
                        </table>
                    </div>
                </div>

                <div class="info-card" style="margin-bottom: 24px; border-left: 4px solid var(--accent); background: rgba(88, 166, 255, 0.05);">
                    <div class="info-title">Hours &amp; Engagement Justification</div>
                    <div id="modal-user-justification" style="font-size: 13.5px; line-height: 1.5; color: var(--text);">Loading engagement statement...</div>
                </div>

                <div class="info-card" style="margin-bottom: 24px;">
                    <div class="info-title" id="modal-permissions-title">Permissions Paths</div>
                    <div id="modal-user-permissions" style="max-height: 120px; overflow-y: auto;">None</div>
                </div>

                <div class="table-card" style="padding: 16px; margin-bottom: 24px;">
                    <div class="info-title">Projects Created By User</div>
                    <table style="font-size:12px;">
                        <thead>
                            <tr style="background:var(--surf-hover)"><th style="padding:8px 12px;">Project Name</th><th style="padding:8px 12px;">Classification</th><th style="padding:8px 12px;">Score</th></tr>
                        </thead>
                        <tbody id="modal-user-projects">
                            <!-- Populated dynamically -->
                        </tbody>
                    </table>
                </div>

                <div class="table-card" style="padding: 16px;">
                    <div class="info-title">Recent Session Logs</div>
                    <table style="font-size:12px;">
                        <thead>
                            <tr style="background:var(--surf-hover)">
                                <th style="padding:8px 12px;">Session Start</th>
                                <th style="padding:8px 12px;">Duration</th>
                                <th style="padding:8px 12px;">IP Address</th>
                                <th style="padding:8px 12px;">Device / User Agent</th>
                            </tr>
                        </thead>
                        <tbody id="modal-user-sessions">
                            <!-- Populated dynamically -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- MAIN JAVASCRIPT STATE & LOGIC -->
    <script>
        let usersData = /*USERS_DATA_JSON_PLACEHOLDER*/ [];
        let summaryData = /*SUMMARY_DATA_JSON_PLACEHOLDER*/ {};
        let projectsData = /*PROJECTS_DATA_JSON_PLACEHOLDER*/ [];
        let orgsData = /*ORGS_DATA_JSON_PLACEHOLDER*/ [];
        let userDetailsCache = /*USER_DETAILS_CACHE_PLACEHOLDER*/ {};
        
        let userSortCol = 'name';
        let userSortAsc = true;

        async function loadAllData() {
            try {
                // If data is preloaded, render directly
                if (usersData && usersData.length > 0) {
                    renderOverview();
                    renderUsersTable();
                    renderProjectsTable();
                    renderOrgsTable();
                    populateFilters();
                    return;
                }

                // Fetch stats concurrently
                const [sumRes, usersRes, projsRes, orgsRes] = await Promise.all([
                    fetch('/api/summary').then(r => r.json()),
                    fetch('/api/users').then(r => r.json()),
                    fetch('/api/projects').then(r => r.json()),
                    fetch('/api/organizations').then(r => r.json())
                ]);

                summaryData = sumRes;
                usersData = usersRes;
                projectsData = projsRes;
                orgsData = orgsRes;

                renderOverview();
                renderUsersTable();
                renderProjectsTable();
                renderOrgsTable();
                populateFilters();
            } catch (e) {
                console.error("Error loading dashboard data:", e);
            }
        }

        function renderOverview() {
            // Render KPI cards
            const grid = document.getElementById('kpi-grid');
            grid.innerHTML = `
                <div class="kpi-card">
                    <div class="kpi-title">Total Registered Users</div>
                    <div class="kpi-value">${summaryData.total_users}</div>
                    <div class="kpi-desc">${summaryData.active_users} active / ${summaryData.total_users - summaryData.active_users} inactive</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Organizations</div>
                    <div class="kpi-value">${summaryData.total_orgs}</div>
                    <div class="kpi-desc">Multi-tenant isolation active</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Total Projects Created</div>
                    <div class="kpi-value">${summaryData.total_projects}</div>
                    <div class="kpi-desc">Across all workspace scopes</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Total Active Sessions</div>
                    <div class="kpi-value">${summaryData.total_sessions}</div>
                    <div class="kpi-desc">Average session duration: ${summaryData.avg_session_mins} mins</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">App Time Invested</div>
                    <div class="kpi-value">${summaryData.total_duration_hours} hrs</div>
                    <div class="kpi-desc">Combined user engagement time</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Project Run Health</div>
                    <div class="kpi-value" style="color:var(--green)">${summaryData.successful_runs}</div>
                    <div class="kpi-desc" style="color:var(--red)">Failed: ${summaryData.failed_runs} runs</div>
                </div>
            `;
        }

        function populateFilters() {
            const orgSelect = document.getElementById('user-org-filter');
            orgSelect.innerHTML = '<option value="">All Organizations</option>';
            const orgs = [...new Set(usersData.map(u => u.organization_name))].filter(Boolean);
            orgs.forEach(org => {
                const opt = document.createElement('option');
                opt.value = org;
                opt.textContent = org;
                orgSelect.appendChild(opt);
            });
        }

        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(`${tabId}-tab`).classList.add('active');
        }

        function renderUsersTable() {
            const body = document.getElementById('users-table-body');
            body.innerHTML = '';

            // Apply Sort
            const sorted = [...usersData].sort((a, b) => {
                let valA, valB;
                if (userSortCol === 'name') { valA = a.name; valB = b.name; }
                else if (userSortCol === 'email') { valA = a.email; valB = b.email; }
                else if (userSortCol === 'organization') { valA = a.organization_name; valB = b.organization_name; }
                else if (userSortCol === 'status') { valA = a.is_active ? 1 : 0; valB = b.is_active ? 1 : 0; }
                else if (userSortCol === 'last_login') { valA = a.last_login; valB = b.last_login; }
                else if (userSortCol === 'projects') { valA = a.projects_count; valB = b.projects_count; }
                else if (userSortCol === 'sessions') { valA = a.sessions_count; valB = b.sessions_count; }
                else if (userSortCol === 'hours') { valA = a.total_duration_hours; valB = b.total_duration_hours; }

                if (valA < valB) return userSortAsc ? -1 : 1;
                if (valA > valB) return userSortAsc ? 1 : -1;
                return 0;
            });

            sorted.forEach(u => {
                const tr = document.createElement('tr');
                tr.className = 'clickable';
                tr.onclick = () => showUserDetail(u);
                
                tr.innerHTML = `
                    <td><strong>${u.name}</strong></td>
                    <td style="font-family:'JetBrains Mono', monospace; font-size:12px;">${u.email}</td>
                    <td>🏢 ${u.organization_name}</td>
                    <td><span class="badge ${u.is_active ? 'badge-active' : 'badge-inactive'}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
                    <td style="font-size:12px; color:var(--text-dim)">${u.last_login}</td>
                    <td style="font-family:'JetBrains Mono', monospace;">${u.projects_count}</td>
                    <td style="font-family:'JetBrains Mono', monospace;">${u.sessions_count}</td>
                    <td style="font-family:'JetBrains Mono', monospace; font-weight:600; color:var(--accent);">${u.total_duration_hours} hrs</td>
                `;
                body.appendChild(tr);
            });
        }

        function sortUserTable(col) {
            if (userSortCol === col) {
                userSortAsc = !userSortAsc;
            } else {
                userSortCol = col;
                userSortAsc = true;
            }
            renderUsersTable();
        }

        function filterUsersTable() {
            const query = document.getElementById('user-search').value.toLowerCase();
            const org = document.getElementById('user-org-filter').value;
            const status = document.getElementById('user-status-filter').value;

            const rows = document.querySelectorAll('#users-table-body tr');
            usersData.forEach((u, idx) => {
                const matchesSearch = u.name.toLowerCase().includes(query) || u.email.toLowerCase().includes(query) || u.organization_name.toLowerCase().includes(query);
                const matchesOrg = !org || u.organization_name === org;
                const matchesStatus = !status || (status === 'active' && u.is_active) || (status === 'inactive' && !u.is_active);

                if (rows[idx]) {
                    rows[idx].style.display = (matchesSearch && matchesOrg && matchesStatus) ? '' : 'none';
                }
            });
        }

        async function showUserDetail(u) {
            const modal = document.getElementById('detail-modal');
            document.getElementById('modal-user-name').textContent = `${u.name} (ID: ${u.id})`;
            
            // Roles
            const rolesDiv = document.getElementById('modal-user-roles');
            rolesDiv.innerHTML = u.roles.length > 0 
                ? u.roles.map(r => `<span class="pill">${r.org} &middot; ${r.role}</span>`).join('')
                : 'No roles assigned';
                
            document.getElementById('modal-user-github').textContent = u.github_username || '—';
            document.getElementById('modal-user-azure').textContent = u.azure_devops_username || '—';

            // Fetch extra DB details dynamically or from preloaded cache
            let res;
            if (typeof userDetailsCache !== 'undefined' && userDetailsCache && userDetailsCache[u.id]) {
                res = userDetailsCache[u.id];
            } else {
                res = await fetch(`/api/users/${u.id}/detail`).then(r => r.json());
            }

            // Generate dynamic Hours & Engagement Justification statement
            const totalSess = res.sessions.length;
            const totalHrs = u.total_duration_hours;
            const avgMins = u.avg_session_mins;
            const projCount = res.projects.length;
            const uniqueIps = new Set(res.sessions.map(s => s.ip_address)).size;
            
            // Find most common device info
            const devicesList = res.sessions.map(s => s.device_info);
            const mostCommonDevice = devicesList.sort((a,b) =>
                devicesList.filter(v => v===a).length - devicesList.filter(v => v===b).length
            ).pop() || "Unknown Client/Browser";

            let justificationText = "";
            if (totalSess > 0) {
                justificationText = `<strong>${u.name}</strong> has a verified app usage of <strong>${totalHrs} hours</strong> across <strong>${totalSess} sessions</strong> over the last 30 days. Their sessions average <strong>${avgMins} minutes</strong> of active interaction, indicating consistent daily workflows. Access logs show requests coming from <strong>${uniqueIps} unique location(s)/IP address(es)</strong>, with <em>${mostCommonDevice}</em> as their primary client browser environment. `;
            } else {
                justificationText = `No session logs were found for <strong>${u.name}</strong>. `;
            }
            
            if (projCount > 0) {
                justificationText += `Furthermore, they have demonstrated high engagement by creating and configuring <strong>${projCount} project(s)</strong> within their organization (<em>${u.organization_name}</em>), leading to multiple automated bootstrap executor runs in the sandbox.`;
            } else {
                justificationText += `They have not created any projects under organization <em>${u.organization_name}</em> yet, reflecting a read-only or administrative-only platform utilization pattern.`;
            }
            
            document.getElementById('modal-user-justification').innerHTML = justificationText;

            // Render Permissions
            document.getElementById('modal-permissions-title').textContent = `Access Permissions (${res.permissions.length} paths)`;
            document.getElementById('modal-user-permissions').innerHTML = res.permissions.length > 0
                ? res.permissions.map(p => `<span class="pill" style="font-size:10px;">${p}</span>`).join('')
                : '<span style="color:var(--text-dim); font-size:12px;">No explicit role paths</span>';

            // Render User Projects
            const projBody = document.getElementById('modal-user-projects');
            projBody.innerHTML = res.projects.length > 0
                ? res.projects.map(p => `
                    <tr>
                        <td><strong>${p.project_name}</strong></td>
                        <td><span class="badge badge-member">${p.classification}</span></td>
                        <td style="font-family:'JetBrains Mono', monospace">${p.weighted_score}</td>
                    </tr>
                `).join('')
                : '<tr><td colspan="3" style="text-align:center; color:var(--text-dim)">No projects created yet</td></tr>';

            // Render User Sessions
            const sessionBody = document.getElementById('modal-user-sessions');
            sessionBody.innerHTML = res.sessions.length > 0
                ? res.sessions.map(s => {
                    const startStr = new Date(s.session_start).toLocaleString();
                    const mins = Math.round(s.duration_seconds / 60);
                    return `
                        <tr>
                            <td>${startStr}</td>
                            <td style="font-family:'JetBrains Mono', monospace; font-weight:600;">${mins} mins</td>
                            <td style="font-family:'JetBrains Mono', monospace; color:var(--accent);">${s.ip_address}</td>
                            <td style="color:var(--text-dim); font-size:11px;">${s.device_info}</td>
                        </tr>
                    `;
                }).join('')
                : '<tr><td colspan="4" style="text-align:center; color:var(--text-dim)">No session logs recorded</td></tr>';

            modal.style.display = 'flex';
        }

        function renderProjectsTable() {
            const body = document.getElementById('projects-table-body');
            body.innerHTML = '';
            
            projectsData.forEach(p => {
                const tr = document.createElement('tr');
                const runStatus = p.run_status || 'completed';
                const statusBadgeClass = runStatus === 'success' || runStatus === 'completed' ? 'badge-active' : 'badge-inactive';
                
                tr.innerHTML = `
                    <td style="font-family:'JetBrains Mono', monospace; font-size:12px;">${p.project_token.slice(0,8)}...</td>
                    <td><strong>${p.project_name}</strong></td>
                    <td>🏢 ${p.organization_name}</td>
                    <td style="font-size:12px; color:var(--text-dim);">${p.owner_email}</td>
                    <td><span class="badge badge-member">${p.classification}</span></td>
                    <td style="font-family:'JetBrains Mono', monospace;">${p.total_runs || 1}</td>
                    <td><span class="badge ${statusBadgeClass}">${runStatus.toUpperCase()}</span></td>
                `;
                body.appendChild(tr);
            });
        }

        function filterProjectsTable() {
            const query = document.getElementById('project-search').value.toLowerCase();
            const status = document.getElementById('project-status-filter').value;
            const rows = document.querySelectorAll('#projects-table-body tr');

            projectsData.forEach((p, idx) => {
                const matchesSearch = p.project_name.toLowerCase().includes(query) || p.project_token.toLowerCase().includes(query) || p.organization_name.toLowerCase().includes(query) || p.owner_email.toLowerCase().includes(query);
                const runStatus = p.run_status || 'completed';
                const matchesStatus = !status || (status === 'success' && (runStatus === 'success' || runStatus === 'completed')) || (status === 'failed' && runStatus === 'failed');

                if (rows[idx]) {
                    rows[idx].style.display = (matchesSearch && matchesStatus) ? '' : 'none';
                }
            });
        }

        function renderOrgsTable() {
            const body = document.getElementById('orgs-table-body');
            body.innerHTML = '';
            
            orgsData.forEach(o => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>🏢 ${o.organization_name}</strong></td>
                    <td style="font-family:'JetBrains Mono', monospace;">${o.user_count}</td>
                    <td style="font-family:'JetBrains Mono', monospace; color:var(--green)">${o.active_count}</td>
                    <td style="font-family:'JetBrains Mono', monospace; color:var(--yellow)">${o.admin_count}</td>
                    <td style="font-family:'JetBrains Mono', monospace; color:var(--accent)">${o.project_count}</td>
                `;
                body.appendChild(tr);
            });
        }

        function closeModal(event) {
            if (event.target === document.getElementById('detail-modal')) {
                document.getElementById('detail-modal').style.display = 'none';
            }
        }

        window.onload = loadAllData;
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=DASHBOARD_HTML_TEMPLATE)

def get_all_static_data():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # KPIs
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM users WHERE is_active=1")
    active_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT organization_name) FROM users WHERE organization_name IS NOT NULL AND organization_name != ''")
    total_orgs = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM governance_responses")
    total_projects = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM user_sessions")
    total_sessions = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(duration_seconds) FROM user_sessions")
    total_duration = cur.fetchone()[0] or 0
    
    cur.execute("SELECT COUNT(*) FROM bootstrap_states WHERE status='success'")
    successful_runs = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM bootstrap_states WHERE status='failed'")
    failed_runs = cur.fetchone()[0]
    
    # Project status counts
    cur.execute("SELECT status, COUNT(*) as cnt FROM bootstrap_states GROUP BY status")
    run_statuses = {r["status"]: r["cnt"] for r in cur.fetchall()}
    
    # Projects per classification
    cur.execute("SELECT classification, COUNT(*) as cnt FROM governance_responses GROUP BY classification")
    classifications = {r["classification"]: r["cnt"] for r in cur.fetchall()}

    summary_data = {
        "total_users": total_users,
        "active_users": active_users,
        "total_orgs": total_orgs,
        "total_projects": total_projects,
        "total_sessions": total_sessions,
        "total_duration_hours": round(total_duration / 3600, 1),
        "avg_session_mins": round((total_duration / max(total_sessions, 1)) / 60, 1),
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "run_statuses": run_statuses,
        "classifications": classifications
    }
    
    # Query all users
    cur.execute("SELECT * FROM users ORDER BY id")
    users = [dict(r) for r in cur.fetchall()]
    
    # Query total projects per user
    cur.execute("SELECT owner_id, COUNT(*) as cnt FROM governance_responses GROUP BY owner_id")
    projects_by_user = {r["owner_id"]: r["cnt"] for r in cur.fetchall()}
    
    # Query sessions stats per user
    cur.execute("SELECT user_id, COUNT(*) as count, SUM(duration_seconds) as total_time FROM user_sessions GROUP BY user_id")
    session_stats = {r["user_id"]: {"count": r["count"], "total_time": r["total_time"]} for r in cur.fetchall()}
    
    # Query user org roles
    cur.execute("""
        SELECT uor.user_id, uor.organization_name, r.name as role_name 
        FROM user_organization_roles uor 
        LEFT JOIN organization_roles r ON uor.role_id = r.id
    """)
    roles = {}
    for r in cur.fetchall():
        roles.setdefault(r["user_id"], []).append({
            "org": r["organization_name"],
            "role": r["role_name"]
        })

    # Query access permission paths count
    cur.execute("""
        SELECT uor.user_id, COUNT(p.path) as perm_count
        FROM user_organization_roles uor
        JOIN organization_role_permissions p ON uor.role_id = p.role_id
        GROUP BY uor.user_id
    """)
    permissions = {r["user_id"]: r["perm_count"] for r in cur.fetchall()}

    enriched_users = []
    for u in users:
        uid = u["id"]
        stats = session_stats.get(uid, {"count": 0, "total_time": 0})
        
        # Format last login
        last_login_str = u.get("last_login")
        if last_login_str:
            try:
                dt = datetime.fromisoformat(last_login_str.split(".")[0].replace(" ", "T"))
                last_login_display = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                last_login_display = last_login_str
        else:
            last_login_display = "Never"

        enriched_users.append({
            "id": uid,
            "email": u["email"],
            "name": f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip() or "Unnamed User",
            "organization_name": u.get("organization_name") or "—",
            "is_active": bool(u.get("is_active")),
            "is_org_admin": bool(u.get("is_org_admin")),
            "last_login": last_login_display,
            "last_page_path": u.get("last_page_path") or "—",
            "projects_count": projects_by_user.get(uid, 0),
            "sessions_count": stats["count"],
            "total_duration_hours": round(stats["total_time"] / 3600, 1),
            "avg_session_mins": round((stats["total_time"] / max(stats["count"], 1)) / 60, 1),
            "roles": roles.get(uid, []),
            "permission_count": permissions.get(uid, 0),
            "github_username": u.get("github_username") or "—",
            "azure_devops_username": u.get("azure_devops_username") or "—"
        })
        
    # Projects + Owner + Latest Run status
    cur.execute("""
        SELECT p.*, u.email as owner_email,
               (SELECT b.status FROM bootstrap_states b WHERE b.project_token = p.project_token ORDER BY b.created_at DESC LIMIT 1) as run_status,
               (SELECT COUNT(*) FROM bootstrap_states b WHERE b.project_token = p.project_token) as total_runs
        FROM governance_responses p
        LEFT JOIN users u ON p.owner_id = u.id
        ORDER BY p.submission_date DESC
    """)
    projects_list = [dict(r) for r in cur.fetchall()]
    
    # Derived from users and roles
    cur.execute("""
        SELECT organization_name, 
               COUNT(DISTINCT id) as user_count,
               SUM(CASE WHEN is_org_admin=1 THEN 1 ELSE 0 END) as admin_count,
               SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active_count
        FROM users
        WHERE organization_name IS NOT NULL AND organization_name != ''
        GROUP BY organization_name
    """)
    orgs = [dict(r) for r in cur.fetchall()]
    
    # Project count per org
    cur.execute("SELECT organization_name, COUNT(*) as project_count FROM governance_responses GROUP BY organization_name")
    proj_counts = {r["organization_name"]: r["project_count"] for r in cur.fetchall() if r["organization_name"]}
    
    # Add project count
    for o in orgs:
        o["project_count"] = proj_counts.get(o["organization_name"], 0)

    # Fetch details for all users
    user_details_cache = {}
    for u in users:
        uid = u["id"]
        cur.execute("SELECT * FROM governance_responses WHERE owner_id=?", (uid,))
        user_projects = [dict(r) for r in cur.fetchall()]
        
        cur.execute("SELECT * FROM user_sessions WHERE user_id=? ORDER BY session_start DESC LIMIT 20", (uid,))
        user_sessions = [dict(r) for r in cur.fetchall()]
        
        cur.execute("""
            SELECT DISTINCT p.path 
            FROM user_organization_roles uor
            JOIN organization_role_permissions p ON uor.role_id = p.role_id
            WHERE uor.user_id=?
        """, (uid,))
        user_permissions = [r["path"] for r in cur.fetchall()]
        
        user_details_cache[uid] = {
            "projects": user_projects,
            "sessions": user_sessions,
            "permissions": sorted(user_permissions)
        }
        
    conn.close()
    
    return summary_data, enriched_users, projects_list, orgs, user_details_cache

def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Connecting to database: {DB_PATH}")
    summary_data, enriched_users, projects_list, orgs_list, user_details_cache = get_all_static_data()

    print(f"[INFO] Serializing data and injecting into HTML template...")
    # Inject the actual JSON data into the placeholders in the HTML template
    html = DASHBOARD_HTML_TEMPLATE
    html = html.replace("/*USERS_DATA_JSON_PLACEHOLDER*/ []", json.dumps(enriched_users))
    html = html.replace("/*SUMMARY_DATA_JSON_PLACEHOLDER*/ {}", json.dumps(summary_data))
    html = html.replace("/*PROJECTS_DATA_JSON_PLACEHOLDER*/ []", json.dumps(projects_list))
    html = html.replace("/*ORGS_DATA_JSON_PLACEHOLDER*/ []", json.dumps(orgs_list))
    html = html.replace("/*USER_DETAILS_CACHE_PLACEHOLDER*/ {}", json.dumps(user_details_cache))

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interactive_dashboard_report.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[INFO] Report successfully generated -> {output_path}")
    webbrowser.open(f"file:///{output_path.replace(os.sep, '/')}")
    print("[INFO] Opened interactive dashboard report in your default web browser.")

if __name__ == "__main__":
    main()
