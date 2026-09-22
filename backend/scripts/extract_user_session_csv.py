#!/usr/bin/env python3
"""
extract_user_session_csv.py - Extract user session and activity data for a specific duration into a CSV file.

Usage Examples:
  # Extract session data for a user by email for a specific date range:
  python backend/extract_user_session_csv.py --email bhabani.b@bourntec.com --start-date 2026-07-01 --end-date 2026-07-31 --output session_data.csv

  # Extract session data for the last 7 days:
  python backend/extract_user_session_csv.py --email bhabani.b@bourntec.com --days 7

  # Extract all session data for a user by ID:
  python backend/extract_user_session_csv.py --user-id 55 --output user_55_sessions.csv

  # Extract session data with summary export mode:
  python backend/extract_user_session_csv.py --email ndash+dsuite@bourntec.com --days 30 --summary-csv user_sessions_summary.csv

  # Interactive prompt mode:
  python backend/extract_user_session_csv.py
"""

import sys
import os
import csv
import argparse
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Ensure backend directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from database import SessionLocal
from sqlalchemy import func, or_, and_
import models


def get_db():
    return SessionLocal()


def parse_datetime(dt_str: str, is_end: bool = False) -> Optional[datetime]:
    """Parses various date/datetime string formats into datetime objects."""
    if not dt_str:
        return None
    
    dt_str = dt_str.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            if fmt in ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"] and is_end:
                # Set time to end of day if only date is specified for end bound
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            return dt
        except ValueError:
            continue

    raise ValueError(f"Could not parse datetime string: '{dt_str}'. Supported formats include YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.")


def find_user(db, identifier: str) -> Optional[models.User]:
    """Locates user by email address or numeric ID."""
    clean_id = str(identifier).strip()
    if clean_id.isdigit():
        user = db.query(models.User).filter(models.User.id == int(clean_id)).first()
        if user:
            return user
    
    return db.query(models.User).filter(func.lower(models.User.email) == clean_id.lower()).first()


def fetch_user_session_events(
    db,
    user: models.User,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    include_ai_usage: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetches all session activity logs and AI usage events for a user within the specified duration window.
    Returns a chronologically sorted list of session event dictionaries.
    """
    events = []

    # 1. Fetch User Activity Logs
    query_act = db.query(models.UserActivityLog).filter(models.UserActivityLog.user_id == user.id)
    if start_dt:
        query_act = query_act.filter(models.UserActivityLog.created_at >= start_dt)
    if end_dt:
        query_act = query_act.filter(models.UserActivityLog.created_at <= end_dt)

    act_logs = query_act.order_by(models.UserActivityLog.created_at.asc()).all()

    for act in act_logs:
        events.append({
            "timestamp": act.created_at.isoformat() if act.created_at else "",
            "datetime": act.created_at,
            "user_id": user.id,
            "user_email": user.email,
            "organization": user.organization_name or "",
            "event_type": "HTTP_ACTIVITY",
            "method": act.method or "",
            "action": act.action or "",
            "path": act.path or "",
            "ip_address": act.ip_address or "",
            "user_agent": act.user_agent or "",
            "details": f"Method: {act.method or 'N/A'}, Path: {act.path or 'N/A'}"
        })

    # 2. Fetch AI Usage Logs (if requested)
    if include_ai_usage and hasattr(models, "AIUsageLog"):
        query_ai = db.query(models.AIUsageLog).filter(models.AIUsageLog.user_id == user.id)
        if start_dt:
            query_ai = query_ai.filter(models.AIUsageLog.created_at >= start_dt)
        if end_dt:
            query_ai = query_ai.filter(models.AIUsageLog.created_at <= end_dt)

        ai_logs = query_ai.order_by(models.AIUsageLog.created_at.asc()).all()

        for ai in ai_logs:
            events.append({
                "timestamp": ai.created_at.isoformat() if ai.created_at else "",
                "datetime": ai.created_at,
                "user_id": user.id,
                "user_email": user.email,
                "organization": user.organization_name or "",
                "event_type": "AI_USAGE",
                "method": "POST",
                "action": f"LLM Call ({ai.model or 'Unknown'})",
                "path": f"Project: {ai.project_token or 'N/A'}",
                "ip_address": "",
                "user_agent": "",
                "details": f"Model: {ai.model}, Prompt Tokens: {ai.prompt_tokens}, Completion Tokens: {ai.completion_tokens}, Cost: ${ai.cost:.6f}"
            })

    # Sort all events chronologically
    events.sort(key=lambda x: x["datetime"] if x["datetime"] else datetime.min)
    return events


def group_events_into_sessions(
    events: List[Dict[str, Any]],
    session_inactivity_minutes: int = 30
) -> List[Dict[str, Any]]:
    """
    Groups individual event logs into distinct logical user login sessions based on inactivity thresholds.
    Default threshold: 30 minutes between requests creates a new session group.
    """
    if not events:
        return []

    sessions = []
    current_session = None

    for ev in events:
        ev_time = ev["datetime"]
        if not ev_time:
            continue

        if current_session is None:
            current_session = {
                "session_id": 1,
                "user_id": ev["user_id"],
                "user_email": ev["user_email"],
                "organization": ev["organization"],
                "session_start": ev_time,
                "session_end": ev_time,
                "duration_seconds": 0,
                "total_events": 1,
                "http_activities": 1 if ev["event_type"] == "HTTP_ACTIVITY" else 0,
                "ai_usage_calls": 1 if ev["event_type"] == "AI_USAGE" else 0,
                "paths_visited": set([ev["path"]]) if ev["path"] else set(),
                "ip_addresses": set([ev["ip_address"]]) if ev["ip_address"] else set()
            }
        else:
            time_gap = (ev_time - current_session["session_end"]).total_seconds()
            if time_gap <= (session_inactivity_minutes * 60):
                # Continuation of current session
                current_session["session_end"] = ev_time
                current_session["duration_seconds"] = int((ev_time - current_session["session_start"]).total_seconds())
                current_session["total_events"] += 1
                if ev["event_type"] == "HTTP_ACTIVITY":
                    current_session["http_activities"] += 1
                elif ev["event_type"] == "AI_USAGE":
                    current_session["ai_usage_calls"] += 1
                if ev["path"]:
                    current_session["paths_visited"].add(ev["path"])
                if ev["ip_address"]:
                    current_session["ip_addresses"].add(ev["ip_address"])
            else:
                # Save completed session and start a new one
                sessions.append(current_session)
                current_session = {
                    "session_id": len(sessions) + 1,
                    "user_id": ev["user_id"],
                    "user_email": ev["user_email"],
                    "organization": ev["organization"],
                    "session_start": ev_time,
                    "session_end": ev_time,
                    "duration_seconds": 0,
                    "total_events": 1,
                    "http_activities": 1 if ev["event_type"] == "HTTP_ACTIVITY" else 0,
                    "ai_usage_calls": 1 if ev["event_type"] == "AI_USAGE" else 0,
                    "paths_visited": set([ev["path"]]) if ev["path"] else set(),
                    "ip_addresses": set([ev["ip_address"]]) if ev["ip_address"] else set()
                }

    if current_session:
        sessions.append(current_session)

    # Convert sets to formatted strings for CSV output
    for s in sessions:
        s["session_start_iso"] = s["session_start"].isoformat()
        s["session_end_iso"] = s["session_end"].isoformat()
        s["duration_formatted"] = str(timedelta(seconds=s["duration_seconds"]))
        s["paths_visited_str"] = "; ".join(list(s["paths_visited"])[:10])
        s["ip_addresses_str"] = "; ".join(list(s["ip_addresses"]))

    return sessions


def export_events_to_csv(events: List[Dict[str, Any]], output_filepath: str) -> str:
    """Writes detailed session events into a CSV file."""
    fieldnames = [
        "timestamp",
        "user_id",
        "user_email",
        "organization",
        "event_type",
        "method",
        "action",
        "path",
        "ip_address",
        "user_agent",
        "details"
    ]

    os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)

    with open(output_filepath, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for ev in events:
            row = {k: ev.get(k, "") for k in fieldnames}
            writer.writerow(row)

    return os.path.abspath(output_filepath)


def export_sessions_summary_to_csv(sessions: List[Dict[str, Any]], output_filepath: str) -> str:
    """Writes aggregated session summary entries into a CSV file."""
    fieldnames = [
        "session_id",
        "user_id",
        "user_email",
        "organization",
        "session_start_iso",
        "session_end_iso",
        "duration_seconds",
        "duration_formatted",
        "total_events",
        "http_activities",
        "ai_usage_calls",
        "ip_addresses_str",
        "paths_visited_str"
    ]

    os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)

    with open(output_filepath, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for s in sessions:
            row = {k: s.get(k, "") for k in fieldnames}
            writer.writerow(row)

    return os.path.abspath(output_filepath)


def extract_user_session_data(
    identifier: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: Optional[int] = None,
    output_csv: Optional[str] = None,
    summary_csv: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Main extraction function:
    1. Validates user existence
    2. Computes start and end datetimes
    3. Fetches session activity and AI usage events
    4. Groups events into login sessions
    5. Exports CSV files
    """
    db = get_db()
    try:
        user = find_user(db, identifier)
        if not user:
            return False, f"User '{identifier}' not found in database."

        start_dt = None
        end_dt = None

        if days is not None:
            end_dt = datetime.utcnow()
            start_dt = end_dt - timedelta(days=days)
        else:
            if start_date:
                start_dt = parse_datetime(start_date, is_end=False)
            if end_date:
                end_dt = parse_datetime(end_date, is_end=True)

        events = fetch_user_session_events(db, user, start_dt, end_dt, include_ai_usage=True)

        if not events:
            dur_info = ""
            if start_dt or end_dt:
                dur_info = f" between {start_dt or 'beginning'} and {end_dt or 'now'}"
            return False, f"No session activity logs found for user '{user.email}'{dur_info}."

        sessions = group_events_into_sessions(events)

        # Generate default output filenames if not provided
        sanitized_email = user.email.replace("@", "_at_").replace(".", "_")
        start_str = start_dt.strftime("%Y%m%d") if start_dt else "start"
        end_str = end_dt.strftime("%Y%m%d") if end_dt else "now"

        if not output_csv and not summary_csv:
            output_csv = f"user_session_details_{sanitized_email}_{start_str}_to_{end_str}.csv"

        created_files = []

        if output_csv:
            path = export_events_to_csv(events, output_csv)
            created_files.append(f"Detailed Events CSV ({len(events)} rows): {path}")

        if summary_csv:
            path = export_sessions_summary_to_csv(sessions, summary_csv)
            created_files.append(f"Session Summary CSV ({len(sessions)} sessions): {path}")

        # Summary statistics display
        min_ev_time = events[0]["timestamp"]
        max_ev_time = events[-1]["timestamp"]

        summary_msg = (
            f"EXTRACTION SUCCESSFUL:\n"
            f"  - User           : {user.email} (ID: {user.id})\n"
            f"  - Organization   : {user.organization_name or 'N/A'}\n"
            f"  - Total Events   : {len(events)}\n"
            f"  - Total Sessions : {len(sessions)}\n"
            f"  - Date Range     : {min_ev_time} to {max_ev_time}\n"
            f"  - Output File(s) :\n" +
            "\n".join([f"      * {f}" for f in created_files])
        )
        return True, summary_msg

    except Exception as e:
        return False, f"Error extracting session data for user '{identifier}': {str(e)}"
    finally:
        db.close()


def interactive_mode():
    """Interactive CLI menu for user session data extraction."""
    print("=" * 70)
    print(" DSuite User Session Data CSV Extractor")
    print("=" * 70)
    email = input("Enter User Email or User ID: ").strip()
    if not email:
        print("[!] User Email or ID is required.")
        return

    print("\nSelect Duration Option:")
    print("  1. Last 24 Hours")
    print("  2. Last 7 Days")
    print("  3. Last 30 Days")
    print("  4. Custom Date Range (Start Date & End Date)")
    print("  5. All Available Duration History")

    choice = input("\nEnter choice (1-5): ").strip()

    days = None
    start_date = None
    end_date = None

    if choice == "1":
        days = 1
    elif choice == "2":
        days = 7
    elif choice == "3":
        days = 30
    elif choice == "4":
        start_date = input("Enter Start Date (e.g. 2026-07-01 or 2026-07-01 00:00:00): ").strip()
        end_date = input("Enter End Date   (e.g. 2026-07-31 or 2026-07-31 23:59:59): ").strip()
    elif choice == "5":
        pass
    else:
        print("[!] Invalid choice. Defaulting to all available duration history.")

    output_file = input("\nEnter output CSV filename [user_session_events.csv]: ").strip() or "user_session_events.csv"
    gen_summary = input("Also generate a Session Summary CSV? (y/N): ").strip().lower()
    summary_file = "user_session_summary.csv" if gen_summary == "y" else None

    ok, msg = extract_user_session_data(
        identifier=email,
        start_date=start_date,
        end_date=end_date,
        days=days,
        output_csv=output_file,
        summary_csv=summary_file
    )
    print("\n" + msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract session data for a duration for a particular user in CSV format.")
    parser.add_argument("--email", type=str, help="User email address")
    parser.add_argument("--user-id", type=str, help="User ID (alternative to --email)")
    parser.add_argument("--start-date", type=str, help="Start date/datetime (e.g. 2026-07-01 or '2026-07-01 00:00:00')")
    parser.add_argument("--end-date", type=str, help="End date/datetime (e.g. 2026-07-31 or '2026-07-31 23:59:59')")
    parser.add_argument("--days", type=int, help="Extract data for the last N days")
    parser.add_argument("--output", "-o", type=str, help="Output CSV filepath for detailed events log")
    parser.add_argument("--summary-csv", type=str, help="Output CSV filepath for aggregated session summary")

    args = parser.parse_args()

    identifier = args.email or args.user_id

    if not identifier:
        interactive_mode()
    else:
        ok, msg = extract_user_session_data(
            identifier=identifier,
            start_date=args.start_date,
            end_date=args.end_date,
            days=args.days,
            output_csv=args.output,
            summary_csv=args.summary_csv
        )
        print(msg)
        if not ok:
            sys.exit(1)
