import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from config import settings
import models
import email_service
from email.message import EmailMessage

logger = logging.getLogger("daily_billing_emails")

# Configuration paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROLS_FILE = os.path.join(BASE_DIR, "email_controls.json")


def load_email_controls() -> Dict[str, Any]:
    """Loads email delivery controls from the local JSON config."""
    default_controls = {
        "system": {
            "enabled": True,
            "utc_hour": 1,
            "utc_minute": 0,
            "send_delay_seconds": 1.0,
            "frequency": "daily",
            "weekly_run_day": 0,
            "max_retries": 3,
            "retry_delay_seconds": 60
        },
        "branding": {
            "company_name": "Bourntec Solutions Inc.",
            "support_email": "support.dsuite@bourntec.com",
            "theme": {
                "primary_color": "#3b82f6",
                "accent_color": "#10b981",
                "bg_dark": "#0f1117",
                "bg_card": "#16181f",
                "text_main": "#e2e8f0",
                "text_muted": "#94a3b8"
            }
        },
        "routing": {
            "cc_rules": {
                "org_rules": {},
                "user_rules": {}
            },
            "bcc_rules": {
                "org_rules": {},
                "user_rules": {}
            },
            "global_cc": [],
            "global_bcc": []
        },
        "filters": {
            "block_list": [],
            "allow_list": [],
            "block_domains": [],
            "allow_domains": [],
            "min_cost_threshold": 0.0001,
            "min_tokens_threshold": 10,
            "skip_zero_usage_users": True,
            "skip_inactive_users": True
        },
        "profiles": {
            "send_to_end_users": True,
            "send_to_org_admins": True,
            "include_model_breakdown": True,
            "include_team_breakdown": True,
            "admin_view_user_emails": True
        },
        "gateways": {
            "override_gateway": "default",
            "sender_display_name": "",
            "reply_to": ""
        },
        "templates": {
            "end_user": "templates/end_user_report.html",
            "org_admin": "templates/org_admin_report.html"
        },
        "last_run_dates": []  # YYYY-MM-DD keys
    }
    
    if not os.path.exists(CONTROLS_FILE):
        try:
            with open(CONTROLS_FILE, "w", encoding="utf-8") as f:
                json.dump(default_controls, f, indent=4)
            logger.info(
                "email_controls.json not found — created with defaults. "
                "Configure via POST /admin/billing-emails/controls to set "
                "scheduler times, allow lists, and recipients for this environment."
            )
            return default_controls
        except Exception as e:
            logger.error(f"Failed to create default email_controls.json: {e}")
            return default_controls
            
    try:
        with open(CONTROLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure nested keys exist recursively
            for k, v in default_controls.items():
                if k not in data:
                    data[k] = v
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if sub_k not in data[k]:
                            data[k][sub_k] = sub_v
                        elif isinstance(sub_v, dict):
                            for nested_k, nested_v in sub_v.items():
                                if nested_k not in data[k][sub_k]:
                                    data[k][sub_k][nested_k] = nested_v
            return data
    except Exception as e:
        logger.error(f"Failed to read email_controls.json, returning defaults: {e}")
        return default_controls


def save_email_controls(controls: Dict[str, Any]) -> None:
    """Saves email controls back to local JSON config."""
    try:
        with open(CONTROLS_FILE, "w", encoding="utf-8") as f:
            json.dump(controls, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save email_controls.json: {e}")


def should_send_email(
    user: models.User,
    daily_cost: float,
    daily_tokens: int,
    controls: Dict[str, Any]
) -> bool:
    """
    Checks if a user should receive emails based on overrides and thresholds.
    """
    email_lower = user.email.lower().strip()
    parts = email_lower.split("@")
    domain = parts[-1] if len(parts) > 1 else ""
    
    filters = controls.get("filters", {})
    
    # 1. Active User check
    if filters.get("skip_inactive_users", True) and not user.is_active:
        return False
        
    # 2. Database opt-out check
    if not user.daily_emails_enabled:
        return False
        
    # 3. Block lists check (Specific email)
    block_list = [x.lower().strip() for x in filters.get("block_list", [])]
    if email_lower in block_list:
        return False
        
    # 4. Block domains check
    block_domains = [x.lower().strip() for x in filters.get("block_domains", [])]
    if domain in block_domains:
        return False
        
    # 5. Allow list checks (Specific email)
    allow_list = [x.lower().strip() for x in filters.get("allow_list", [])]
    email_allowed = ("*" in allow_list) or (email_lower in allow_list)
            
    # 6. Allow domains checks
    allow_domains = [x.lower().strip() for x in filters.get("allow_domains", [])]
    domain_allowed = ("*" in allow_domains) or (domain in allow_domains)
    
    if not email_allowed or not domain_allowed:
        return False
            
    # 7. Zero usage checks
    if filters.get("skip_zero_usage_users", True) and daily_tokens == 0:
        logger.info(f"Daily report skipped for {user.email} (Zero usage detected)")
        return False
            
    # 8. Cost & Token threshold checks
    min_cost = float(filters.get("min_cost_threshold", 0.0001))
    min_tokens = int(filters.get("min_tokens_threshold", 10))
    
    if daily_cost < min_cost and daily_tokens < min_tokens:
        logger.info(f"Daily report skipped for {user.email} (Cost: {daily_cost} < {min_cost} AND Tokens: {daily_tokens} < {min_tokens})")
        return False
        
    return True


def format_tokens(num: int) -> str:
    """Format token count with comma separator."""
    return f"{num:,}"


def format_cost(val: float) -> str:
    """Format float cost to 4 decimal places."""
    return f"${val:.4f}"


def mask_email(email: str) -> str:
    """Mask email for privacy compliance (e.g. siba.p@bourntec.com -> si***@bourntec.com)."""
    parts = email.split("@")
    if len(parts) != 2:
        return email
    local, domain = parts
    if len(local) <= 2:
        masked_local = local + "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def render_template(template_path: str, context: Dict[str, Any]) -> str:
    """
    Loads an external HTML file and replaces {{ placeholder }} variables.
    """
    abs_path = os.path.join(BASE_DIR, template_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Email template file not found at: {abs_path}")
        
    with open(abs_path, "r", encoding="utf-8") as f:
        html = f.read()
        
    for key, value in context.items():
        placeholder = "{{" + f" {key} " + "}}"
        placeholder_no_spaces = "{{" + key + "}}"
        html = html.replace(placeholder, str(value))
        html = html.replace(placeholder_no_spaces, str(value))
        
    return html


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM SENDER DISPATCH
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_email_message(message: EmailMessage, controls: Dict[str, Any]) -> None:
    """
    Custom email delivery dispatcher supporting SMTP vs Graph API overrides,
    custom reply-to headers, and display names.
    """
    gateways = controls.get("gateways", {})
    override = gateways.get("override_gateway", "default").lower().strip()
    
    # Custom headers
    reply_to = gateways.get("reply_to", "").strip()
    if reply_to:
        if "Reply-To" in message:
            message.replace_header("Reply-To", reply_to)
        else:
            message["Reply-To"] = reply_to
        
    sender_display_name = gateways.get("sender_display_name", "").strip()
    if sender_display_name:
        from_email = str(settings.smtp_from_email or "").strip()
        message.replace_header("From", f'"{sender_display_name}" <{from_email}>')

    if override == "smtp":
        import smtplib
        sender_email = str(settings.smtp_from_email or "").strip()
        smtp_host = str(settings.smtp_host or "").strip()
        smtp_password = str(settings.smtp_password or "")
        timeout = max(int(settings.smtp_timeout_seconds or 20), 1)
        
        if not smtp_host:
            raise RuntimeError("SMTP gateway forced but SMTP_HOST is missing.")
            
        smtp_cls = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_cls(smtp_host, settings.smtp_port, timeout=timeout) as server:
            if not settings.smtp_use_ssl and settings.smtp_use_tls:
                server.ehlo()
                server.starttls()
                server.ehlo()
            if sender_email:
                server.login(sender_email, smtp_password)
            server.send_message(message)
            
    elif override == "graph_api":
        import msal
        sender_email = str(settings.smtp_from_email or "").strip()
        tenant_id = str(settings.microsoft_tenant_id or "").strip()
        client_id = str(settings.microsoft_client_id or "").strip()
        client_secret = str(settings.microsoft_client_secret or "").strip()
        
        if not tenant_id or not client_id or not client_secret:
            raise RuntimeError("Microsoft Graph API gateway forced but configurations are missing.")
            
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret
        )
        scopes = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_silent(scopes, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=scopes)
        if "access_token" not in result:
            raise RuntimeError(f"Failed to acquire Microsoft OAuth token: {result.get('error')}")
            
        access_token = result["access_token"]
        email_service._send_email_graph_api(message, access_token, sender_email)
    else:
        # Default behavior
        email_service._send_email_message(message)


# ─────────────────────────────────────────────────────────────────────────────
# CORE SENDING IMPLEMENTATION
# ─────────────────────────────────────────────────────────────────────────────

async def send_daily_billing_emails(
    db: Session,
    run_date: Optional[datetime] = None,
    target_email: Optional[str] = None,
    skip_logging_run_date: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Asynchronously queries daily AI token metrics and dispatches reports.
    Supports comprehensive branding, compliance routing (BCC/CC), throttling, and skips.
    """
    email_service.ensure_email_delivery_configured()
    
    if run_date is None:
        run_date = datetime.utcnow()
        
    date_str = run_date.strftime("%B %d, %Y")
    date_key = run_date.strftime("%Y-%m-%d")
    
    start_dt = datetime(run_date.year, run_date.month, run_date.day, 0, 0, 0)
    end_dt = run_date
    
    controls = load_email_controls()
    branding = controls.get("branding", {})
    theme = branding.get("theme", {})
    routing = controls.get("routing", {})
    profiles = controls.get("profiles", {})
    templates = controls.get("templates", {})
    system = controls.get("system", {})
    
    # 1. Fetch active users (limit to target_email if provided)
    query = db.query(models.User).filter(models.User.is_active == True)
    if target_email:
        query = query.filter(models.User.email == target_email.strip())
    active_users = query.all()
    
    # Group users by organization
    org_groups: Dict[str, List[models.User]] = {}
    for u in active_users:
        org = (u.organization_name or "").strip()
        if org:
            org_key = org.lower()
            if org_key not in org_groups:
                org_groups[org_key] = []
            org_groups[org_key].append(u)

    # 2. Fetch all AIUsageLogs for yesterday
    logs_query = db.query(models.AIUsageLog).filter(
        models.AIUsageLog.created_at >= start_dt,
        models.AIUsageLog.created_at <= end_dt
    )
    if target_email and active_users:
        logs_query = logs_query.filter(models.AIUsageLog.user_id == active_users[0].id)
        
    logs = logs_query.all()
    
    # Aggregate logs
    user_logs: Dict[int, List[models.AIUsageLog]] = {}
    for l in logs:
        if l.user_id:
            if l.user_id not in user_logs:
                user_logs[l.user_id] = []
            user_logs[l.user_id].append(l)

    # Calculate user statistics
    user_stats_cache = {}
    for uid, u_logs in user_logs.items():
        total_tok = 0
        prompt_tok = 0
        compl_tok = 0
        cost = 0.0
        model_breakdown = {}
        
        for l in u_logs:
            p = l.prompt_tokens or 0
            c = l.completion_tokens or 0
            cost += l.cost or 0.0
            prompt_tok += p
            compl_tok += c
            total_tok += (p + c)
            
            m = l.model or "unknown"
            if m not in model_breakdown:
                model_breakdown[m] = {"model": m, "requests": 0, "prompt": 0, "completion": 0, "cost": 0.0}
            model_breakdown[m]["requests"] += 1
            model_breakdown[m]["prompt"] += p
            model_breakdown[m]["completion"] += c
            model_breakdown[m]["cost"] += l.cost or 0.0
            
        # Silently fold in infra cost ($0.70/hr based on active AI usage duration)
        # This is never labelled as "infra cost" anywhere in the email
        timestamps = [l.created_at for l in u_logs if l.created_at]
        if timestamps:
            usage_dur_sec = (max(timestamps) - min(timestamps)).total_seconds()
        else:
            usage_dur_sec = 0.0
        infra_cost = (usage_dur_sec / 3600.0) * 0.7
        total_cost = cost + infra_cost

        user_stats_cache[uid] = {
            "total_tokens": total_tok,
            "prompt_tokens": prompt_tok,
            "completion_tokens": compl_tok,
            "cost": round(total_cost, 4),
            "model_breakdown": list(model_breakdown.values())
        }

    results = {
        "date": date_key,
        "processed_users": len(active_users),
        "emails_sent": 0,
        "details": []
    }

    # 3. Deliver reports to users
    for idx, user in enumerate(active_users):
        user_metrics = user_stats_cache.get(user.id, {
            "total_tokens": 0, "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "model_breakdown": []
        })
        
        is_admin = bool(user.is_org_admin and user.organization_name)
        
        # Check profile flags
        if is_admin and not profiles.get("send_to_org_admins", True):
            results["details"].append({"email": user.email, "status": "skipped_by_admin_profile", "is_admin": True})
            continue
        if not is_admin and not profiles.get("send_to_end_users", True):
            results["details"].append({"email": user.email, "status": "skipped_by_user_profile", "is_admin": False})
            continue
        
        # Check cost/token thresholds (ignore thresholds for target force triggers)
        if not target_email and not should_send_email(user, user_metrics["cost"], user_metrics["total_tokens"], controls):
            try:
                audit_log = models.DailyBillingEmailLog(
                    user_id=user.id,
                    email=user.email,
                    date_key=date_key,
                    status="skipped_by_filters",
                    total_tokens=user_metrics["total_tokens"],
                    total_cost=user_metrics["cost"],
                    is_admin_report=is_admin
                )
                db.add(audit_log)
                db.commit()
            except Exception as dbe:
                logger.error(f"Audit log database insertion failed: {dbe}")
                db.rollback()
                
            results["details"].append({"email": user.email, "status": "skipped_by_filters", "is_admin": is_admin})
            continue
            
        # Parse compliance CC/BCC routing rules
        cc_list = list(routing.get("global_cc", []))
        bcc_list = list(routing.get("global_bcc", []))
        
        # User-level compliance CC/BCC
        user_cc = routing.get("cc_rules", {}).get("user_rules", {}).get(user.email.lower().strip())
        if user_cc:
            cc_list.extend(user_cc if isinstance(user_cc, list) else [user_cc])
            
        user_bcc = routing.get("bcc_rules", {}).get("user_rules", {}).get(user.email.lower().strip())
        if user_bcc:
            bcc_list.extend(user_bcc if isinstance(user_bcc, list) else [user_bcc])
            
        # Organization-level compliance CC/BCC
        if user.organization_name:
            org_key = user.organization_name.lower().strip()
            org_cc = routing.get("cc_rules", {}).get("org_rules", {}).get(org_key)
            if org_cc:
                cc_list.extend(org_cc if isinstance(org_cc, list) else [org_cc])
                
            org_bcc = routing.get("bcc_rules", {}).get("org_rules", {}).get(org_key)
            if org_bcc:
                bcc_list.extend(org_bcc if isinstance(org_bcc, list) else [org_bcc])
                
        cc_list = [x.strip() for x in cc_list if x.strip()]
        bcc_list = [x.strip() for x in bcc_list if x.strip()]
        
        cc_header = ", ".join(cc_list) if cc_list else None
        bcc_header = ", ".join(bcc_list) if bcc_list else None
            
        subject = f"Daily Utilization & Cost Report - {date_str}"
        greeting = user.first_name or "there"
        
        # Compute dynamic values
        total_tokens = user_metrics["total_tokens"]
        prompt_tokens = user_metrics["prompt_tokens"]
        completion_tokens = user_metrics["completion_tokens"]
        total_cost = user_metrics["cost"]

        # Percentages
        if total_tokens > 0:
            prompt_pct = int(round((prompt_tokens / total_tokens) * 100))
            completion_pct = 100 - prompt_pct
            # Use full total_cost (token + infra) so avg aligns with displayed total
            avg_cost = (total_cost / total_tokens) * 1000
        else:
            prompt_pct = 50
            completion_pct = 50
            avg_cost = 0.0

        avg_cost_str = f"${avg_cost:.4f}"
        
        # Inject branding and template variables
        template_context = {
            "company_name": branding.get("company_name", "DSuite"),
            "support_email": branding.get("support_email", "support@dsuite.com"),
            "logo_url": branding.get("logo_url", "https://dsuite.com/logo.png"),
            "primary_color": theme.get("primary_color", "#3b82f6"),
            "accent_color": theme.get("accent_color", "#10b981"),
            "bg_dark": theme.get("bg_dark", "#0f1117"),
            "bg_card": theme.get("bg_card", "#16181f"),
            "text_main": theme.get("text_main", "#e2e8f0"),
            "text_muted": theme.get("text_muted", "#94a3b8"),
            "date_str": date_str,
            "greeting": greeting,
            "current_year": str(datetime.utcnow().year),
            "prompt_pct": prompt_pct,
            "completion_pct": completion_pct,
            "avg_cost_per_1k": avg_cost_str
        }
        
        try:
            if is_admin:
                org_key = user.organization_name.lower().strip()
                org_users = org_groups.get(org_key, [])
                
                team_stats = []
                org_total_tokens = 0
                org_total_cost = 0.0
                org_prompt_tokens = 0
                org_completion_tokens = 0
                
                for tu in org_users:
                    tu_metrics = user_stats_cache.get(tu.id, {
                        "total_tokens": 0, "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0
                    })
                    org_total_tokens += tu_metrics["total_tokens"]
                    org_total_cost += tu_metrics["cost"]
                    org_prompt_tokens += tu_metrics["prompt_tokens"]
                    org_completion_tokens += tu_metrics["completion_tokens"]
                    
                    tu_email = mask_email(tu.email) if not profiles.get("admin_view_user_emails", True) else tu.email
                    
                    team_stats.append({
                        "email": tu_email,
                        "name": f"{tu.first_name or ''} {tu.last_name or ''}".strip(),
                        "tokens": tu_metrics["total_tokens"],
                        "cost": tu_metrics["cost"]
                    })
                    
                # Organization aggregated percentages
                if org_total_tokens > 0:
                    org_prompt_pct = int(round((org_prompt_tokens / org_total_tokens) * 100))
                    org_completion_pct = 100 - org_prompt_pct
                    org_avg_cost = (org_total_cost / org_total_tokens) * 1000
                else:
                    org_prompt_pct = 50
                    org_completion_pct = 50
                    org_avg_cost = 0.0
                    
                org_avg_cost_str = f"${org_avg_cost:.4f}"
                
                # Format model breakdown (Admin's personal usage)
                admin_model_rows = ""
                if profiles.get("include_model_breakdown", True) and user_metrics["model_breakdown"]:
                    for item in user_metrics["model_breakdown"]:
                        admin_model_rows += f"""
                        <tr class="mrow">
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:left;">
                                <span style="display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:8px;background:{theme.get('accent_color', '#10b981')};"></span>{item['model']}
                            </td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:center;">{item['requests']}</td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;">{format_tokens(item['prompt'])}</td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;">{format_tokens(item['completion'])}</td>
                            <td class="mrow-cost" style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;font-weight:700;color:{theme.get('accent_color', '#10b981')}!important;">{format_cost(item['cost'])}</td>
                        </tr>
                        """
                else:
                    admin_model_rows = f"""
                    <tr>
                        <td colspan="5" style="padding:16px;color:{theme.get('text_muted', '#94a3b8')};text-align:center;font-style:italic;">
                            No breakdown details requested.
                        </td>
                    </tr>
                    """

                # Format team stats rows
                team_rows = ""
                if profiles.get("include_team_breakdown", True) and team_stats:
                    for member in team_stats:
                        name_label = member['name'] if member['name'].strip() else member['email'].split('@')[0]
                        team_rows += f"""
                        <tr class="mrow">
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:left;">
                                <div style="font-weight:600;">{name_label}</div>
                                <div style="font-size:10px;color:{theme.get('text_muted', '#94a3b8')};">{member['email']}</div>
                            </td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;">{format_tokens(member['tokens'])}</td>
                            <td class="mrow-cost" style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;font-weight:700;color:{theme.get('accent_color', '#10b981')}!important;">{format_cost(member['cost'])}</td>
                        </tr>
                        """
                else:
                    team_rows = f"""
                    <tr>
                        <td colspan="3" style="padding:20px;color:{theme.get('text_muted', '#94a3b8')};text-align:center;font-style:italic;">
                            Team member list breakdown is disabled.
                        </td>
                    </tr>
                    """
                
                template_context.update({
                    "org_name": user.organization_name,
                    "org_total_tokens": format_tokens(org_total_tokens),
                    "org_total_cost": format_cost(org_total_cost),
                    "org_prompt_tokens": format_tokens(org_prompt_tokens),
                    "org_completion_tokens": format_tokens(org_completion_tokens),
                    "org_prompt_pct": org_prompt_pct,
                    "org_completion_pct": org_completion_pct,
                    "org_avg_cost_per_1k": org_avg_cost_str,
                    "team_rows": team_rows,
                    "admin_model_rows": admin_model_rows
                })
                
                html = render_template(templates.get("org_admin", "templates/org_admin_report.html"), template_context)
            else:
                # Regular end user report
                model_rows = ""
                if profiles.get("include_model_breakdown", True) and user_metrics["model_breakdown"]:
                    for item in user_metrics["model_breakdown"]:
                        model_rows += f"""
                        <tr class="mrow">
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:left;">
                                <span style="display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:8px;background:{theme.get('accent_color', '#10b981')};"></span>{item['model']}
                            </td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:center;">{item['requests']}</td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;">{format_tokens(item['prompt'])}</td>
                            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;">{format_tokens(item['completion'])}</td>
                            <td class="mrow-cost" style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;font-weight:700;color:{theme.get('accent_color', '#10b981')}!important;">{format_cost(item['cost'])}</td>
                        </tr>
                        """
                else:
                    model_rows = f"""
                    <tr>
                        <td colspan="5" style="padding:24px;color:{theme.get('text_muted', '#94a3b8')};text-align:center;font-style:italic;">
                            Detail model breakdown table is disabled.
                        </td>
                    </tr>
                    """

                template_context.update({
                    "total_tokens": format_tokens(total_tokens),
                    "prompt_tokens": format_tokens(prompt_tokens),
                    "completion_tokens": format_tokens(completion_tokens),
                    "total_cost": format_cost(total_cost),
                    "model_rows": model_rows
                })
                
                html = render_template(templates.get("end_user", "templates/end_user_report.html"), template_context)
                
            # Build Message
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = email_service._from_header()
            message["To"] = user.email
            if cc_header:
                message["Cc"] = cc_header
            if bcc_header:
                message["Bcc"] = bcc_header
            
            message.set_content(
                f"Daily token utilization report for today ({date_str}). Please view in an HTML-compatible client."
            )
            message.add_alternative(html, subtype="html")
            
            status_str = "success"
            if dry_run:
                status_str = "dry_run_success"
                logger.info(f"[DRY-RUN] Skipped email dispatch delivery to: {user.email}")
            else:
                dispatch_email_message(message, controls)
                results["emails_sent"] += 1
                logger.info(f"Daily utilization report delivered to: {user.email}")
                
            results["details"].append({"email": user.email, "status": status_str, "is_admin": is_admin})
            
            # Record audit log
            try:
                audit_log = models.DailyBillingEmailLog(
                    user_id=user.id,
                    email=user.email,
                    date_key=date_key,
                    status=status_str,
                    total_tokens=total_tokens,
                    total_cost=total_cost,
                    is_admin_report=is_admin,
                    cc_recipients=cc_header
                )
                db.add(audit_log)
                db.commit()
            except Exception as dbe:
                logger.error(f"Audit log database insertion failed: {dbe}")
                db.rollback()
            
        except Exception as e:
            logger.error(f"Failed to generate/deliver daily utilization report to {user.email}: {e}")
            results["details"].append({"email": user.email, "status": f"failed: {str(e)}", "is_admin": is_admin})
            
            try:
                audit_log = models.DailyBillingEmailLog(
                    user_id=user.id,
                    email=user.email,
                    date_key=date_key,
                    status="failed",
                    error_message=str(e),
                    total_tokens=user_metrics["total_tokens"],
                    total_cost=user_metrics["cost"],
                    is_admin_report=is_admin,
                    cc_recipients=cc_header
                )
                db.add(audit_log)
                db.commit()
            except Exception as dbe:
                logger.error(f"Audit log database insertion failed: {dbe}")
                db.rollback()
                
        # Throttling
        send_delay = float(system.get("send_delay_seconds", 1.0))
        if send_delay > 0.0 and idx < len(active_users) - 1:
            logger.info(f"Throttling delay: Sleeping for {send_delay} seconds...")
            await asyncio.sleep(send_delay)

    # Save run date
    if not target_email and not skip_logging_run_date and not dry_run:
        controls = load_email_controls()
        if date_key not in controls.get("last_run_dates", []):
            controls.get("last_run_dates", []).append(date_key)
            if len(controls["last_run_dates"]) > 30:
                controls["last_run_dates"].pop(0)
            save_email_controls(controls)
        
    return results


async def send_super_user_billing_report(
    db: Session,
    run_date: Optional[datetime] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Sends a consolidated billing report to configured super users.
    Filters logs starting from midnight of run_date until run_date.
    """
    email_service.ensure_email_delivery_configured()
    
    if run_date is None:
        run_date = datetime.utcnow()
        
    # Start: Midnight of run_date
    start_dt = datetime(run_date.year, run_date.month, run_date.day, 0, 0, 0)
    end_dt = run_date
    
    date_str = run_date.strftime("%B %d, %Y")
    
    controls = load_email_controls()
    super_user_config = controls.get("super_user", {})
    if not super_user_config.get("enabled", True):
        logger.info("Super user billing report is disabled in controls, skipping.")
        return {"status": "skipped", "reason": "disabled"}
        
    recipients = super_user_config.get("recipients", [])
    if not recipients:
        logger.warning("No super user recipients configured, skipping report.")
        return {"status": "skipped", "reason": "no_recipients"}
        
    branding = controls.get("branding", {})
    theme = branding.get("theme", {})
    templates = controls.get("templates", {})
    
    # Query all users to construct maps
    all_users = db.query(models.User).all()
    user_to_org = {u.id: (u.organization_name or "Individual").strip() for u in all_users}
    
    # Count members per organization
    org_member_counts = {}
    for u in all_users:
        org_name = (u.organization_name or "Individual").strip()
        org_member_counts[org_name] = org_member_counts.get(org_name, 0) + 1
        
    # Query usage logs in window
    logs = db.query(models.AIUsageLog).filter(
        models.AIUsageLog.created_at >= start_dt,
        models.AIUsageLog.created_at <= end_dt
    ).all()
    
    org_breakdown = {}
    global_tokens = 0
    global_prompt_tokens = 0
    global_completion_tokens = 0
    global_cost = 0.0
    
    # Pre-populate all active organizations
    for u in all_users:
        org_name = (u.organization_name or "Individual").strip()
        if org_name not in org_breakdown:
            org_breakdown[org_name] = {
                "tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost": 0.0,
                "requests": 0
            }
            
    for log in logs:
        org_name = user_to_org.get(log.user_id, "Individual")
        if org_name not in org_breakdown:
            org_breakdown[org_name] = {
                "tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost": 0.0,
                "requests": 0
            }
        p = log.prompt_tokens or 0
        c = log.completion_tokens or 0
        cost_val = log.cost or 0.0

        org_breakdown[org_name]["tokens"] += (p + c)
        org_breakdown[org_name]["prompt_tokens"] += p
        org_breakdown[org_name]["completion_tokens"] += c
        org_breakdown[org_name]["cost"] += cost_val
        org_breakdown[org_name]["requests"] += 1

        global_tokens += (p + c)
        global_prompt_tokens += p
        global_completion_tokens += c
        global_cost += cost_val

    # Silently fold per-user infra cost ($0.70/hr from active AI usage duration)
    # into org breakdown totals — never labelled as infra cost in the email output
    user_timestamps: dict = {}
    for log in logs:
        if log.user_id and log.created_at:
            user_timestamps.setdefault(log.user_id, []).append(log.created_at)
    for uid, ts_list in user_timestamps.items():
        if ts_list:
            dur_sec = (max(ts_list) - min(ts_list)).total_seconds()
        else:
            dur_sec = 0.0
        u_infra = (dur_sec / 3600.0) * 0.7
        org_name = user_to_org.get(uid, "Individual")
        if org_name in org_breakdown:
            org_breakdown[org_name]["cost"] += u_infra
        global_cost += u_infra
        
    # Calculate global stats
    if global_tokens > 0:
        prompt_pct = int(round((global_prompt_tokens / global_tokens) * 100))
        completion_pct = 100 - prompt_pct
        # Use full global_cost (token + infra) so avg aligns with displayed total
        avg_cost = (global_cost / global_tokens) * 1000
    else:
        prompt_pct = 50
        completion_pct = 50
        avg_cost = 0.0

    global_avg_cost_str = f"${avg_cost:.4f}"
    
    # Format organization breakdown rows HTML
    org_rows = ""
    # Sort organizations by cost descending
    sorted_orgs = sorted(org_breakdown.keys(), key=lambda k: org_breakdown[k]["cost"], reverse=True)
    for org_name in sorted_orgs:
        stats = org_breakdown[org_name]
        member_count = org_member_counts.get(org_name, 0)
        org_rows += f"""
        <tr class="mrow">
            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:left;">
                <div style="font-weight:600;">{org_name}</div>
            </td>
            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:center;">{member_count}</td>
            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:center;">{stats['requests']}</td>
            <td style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;">{format_tokens(stats['tokens'])}</td>
            <td class="mrow-cost" style="padding:11px 14px;border-bottom:1px solid {theme.get('primary_color', '#3b82f6')}11;text-align:right;font-weight:700;color:{theme.get('accent_color', '#10b981')}!important;">{format_cost(stats['cost'])}</td>
        </tr>
        """
        
    # Prepare template context
    template_context = {
        "company_name": branding.get("company_name", "DSuite"),
        "support_email": branding.get("support_email", "support@dsuite.com"),
        "primary_color": theme.get("primary_color", "#3b82f6"),
        "accent_color": theme.get("accent_color", "#10b981"),
        "bg_dark": theme.get("bg_dark", "#0f1117"),
        "bg_card": theme.get("bg_card", "#16181f"),
        "text_main": theme.get("text_main", "#e2e8f0"),
        "text_muted": theme.get("text_muted", "#94a3b8"),
        "date_str": date_str,
        "greeting": "Administrator",
        "current_year": str(datetime.utcnow().year),
        "global_total_tokens": format_tokens(global_tokens),
        "global_total_cost": format_cost(global_cost),
        "prompt_pct": prompt_pct,
        "completion_pct": completion_pct,
        "global_prompt_tokens": format_tokens(global_prompt_tokens),
        "global_completion_tokens": format_tokens(global_completion_tokens),
        "global_avg_cost_per_1k": global_avg_cost_str,
        "org_rows": org_rows
    }
    
    html = render_template(templates.get("super_user", "templates/super_user_report.html"), template_context)
    
    if dry_run:
        logger.info(f"[DRY RUN] Would send super user billing report to: {recipients}")
        return {
            "status": "dry_run_success",
            "recipients": recipients,
            "org_count": len(sorted_orgs),
            "global_tokens": global_tokens,
            "global_cost": global_cost
        }
        
    # CC and BCC rules for super user
    cc_list = super_user_config.get("cc_rules", [])
    bcc_list = super_user_config.get("bcc_rules", [])
    
    cc_header = ", ".join(cc_list) if cc_list else None
    bcc_header = ", ".join(bcc_list) if bcc_list else None
    
    subject = f"Super User Daily Cost & Token Summary - {date_str}"
    
    # Send
    for email in recipients:
        try:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = email_service._from_header()
            message["To"] = email
            if cc_header:
                message["Cc"] = cc_header
            if bcc_header:
                message["Bcc"] = bcc_header
            message.set_content(
                f"Consolidated organization utilization ledger report for {date_str}."
            )
            message.add_alternative(html, subtype="html")
            
            dispatch_email_message(message, controls)
            logger.info(f"Super user billing report delivered to: {email}")
        except Exception as e:
            logger.error(f"Failed to deliver super user report to {email}: {e}")
            
    return {
        "status": "success",
        "recipients": recipients,
        "org_count": len(sorted_orgs),
        "global_tokens": global_tokens,
        "global_cost": global_cost
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND SCHEDULER TASK
# ─────────────────────────────────────────────────────────────────────────────

async def daily_billing_email_scheduler() -> None:
    """
    Infinite scheduler task loop running in FastAPI background lifespan.
    """
    logger.info("Initializing daily utilization email background scheduler loop.")
    await asyncio.sleep(60)
    
    from database import SessionLocal
    
    while True:
        try:
            if not settings.daily_billing_email_enabled:
                await asyncio.sleep(3600)
                continue
                
            controls = load_email_controls()
            system = controls.get("system", {})
            
            if not system.get("enabled", True):
                await asyncio.sleep(1800)
                continue
                
            now = datetime.utcnow()
            target_hour = system.get("utc_hour", settings.daily_billing_email_hour)
            target_minute = system.get("utc_minute", 0)
            
            run_date_key = now.strftime("%Y-%m-%d")
            already_run = run_date_key in controls.get("last_run_dates", [])
            
            # Construct target trigger time for today in UTC
            scheduled_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            
            if now >= scheduled_today and not already_run:
                logger.info(f"Triggering scheduled daily utilization reports for: {run_date_key}")
                
                try:
                    email_service.ensure_email_delivery_configured()
                    
                    db = SessionLocal()
                    try:
                        await send_daily_billing_emails(db, now)
                        await send_super_user_billing_report(db, now)
                    finally:
                        db.close()
                except RuntimeError as re:
                    logger.warning(f"Skipping scheduled daily emails (delivery settings not configured): {re}")
                except Exception as ex:
                    logger.exception(f"Exception during background scheduled utilization reports: {ex}")
            
            # Poll configuration and time every 60 seconds for optimal efficiency
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("Daily utilization email background scheduler cancelled.")
            break
        except Exception as e:
            logger.exception(f"Unexpected error in daily billing email scheduler loop: {e}")
            await asyncio.sleep(300)
