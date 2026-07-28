"""
Script to create or promote a user to Super Admin in DSuite.

Usage:
  python backend/create_superadmin.py --email admin@example.com --password "SecurePass123!" --org "Bourntec"
  
Or run interactively:
  python backend/create_superadmin.py
"""
import sys
import os
import argparse

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
from models import User, OrganizationAgentQuota
from auth import get_password_hash
from migrations.add_superadmin_and_capacity_requests import upgrade as run_migrations

def setup_superadmin(email: str, password: str = None, org_name: str = "Bourntec"):
    """
    Creates a new Super Admin user or promotes an existing user to Super Admin.
    """
    # 1. Run migrations first to ensure columns exist
    try:
        run_migrations()
    except Exception as e:
        print(f"Warning running migrations: {e}")

    db = SessionLocal()
    try:
        email_clean = email.strip().lower()
        user = db.query(User).filter(User.email == email_clean).first()

        if user:
            print(f"Found existing user: {user.email}")
            user.is_super_admin = True
            user.is_org_admin = True
            if password:
                user.hashed_password = get_password_hash(password)
                print("Updated password for user.")
            if org_name and not user.organization_name:
                user.organization_name = org_name
            db.commit()
            db.refresh(user)
            print(f"[SUCCESS] Successfully promoted '{user.email}' to SUPER ADMIN (User ID: {user.id})!")
        else:
            if not password:
                raise ValueError("Password is required to create a new Super Admin user.")

            new_user = User(
                email=email_clean,
                hashed_password=get_password_hash(password),
                organization_name=org_name or "Bourntec",
                is_org_admin=True,
                is_super_admin=True,
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            print(f"[SUCCESS] Successfully created new SUPER ADMIN user: '{new_user.email}' (User ID: {new_user.id})!")

        # Initialize organization quota if missing
        if org_name:
            quota = db.query(OrganizationAgentQuota).filter(
                OrganizationAgentQuota.organization_name == org_name
            ).first()
            if not quota:
                new_quota = OrganizationAgentQuota(
                    organization_name=org_name,
                    max_agent_capacity=10,
                    shared_quota=10,
                    dedicated_quota=10
                )
                db.add(new_quota)
                db.commit()
                print(f"[OK] Initialized organization quota for '{org_name}' with 10 max agent capacity.")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error setting up Super Admin: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or promote a user to Super Admin")
    parser.add_argument("--email", type=str, help="Email address of the Super Admin")
    parser.add_argument("--password", type=str, help="Password for the Super Admin")
    parser.add_argument("--org", type=str, default="Bourntec", help="Organization name (default: Bourntec)")

    args = parser.parse_args()

    email = args.email
    password = args.password
    org = args.org

    if not email:
        print("=" * 60)
        print("DSuite Super Admin Setup Utility")
        print("=" * 60)
        email = input("Enter Super Admin Email: ").strip()
        if not email:
            print("Error: Email is required.")
            sys.exit(1)

        password = input("Enter Super Admin Password (leave blank if user exists to keep current password): ").strip()
        org_input = input("Enter Organization Name [Bourntec]: ").strip()
        if org_input:
            org = org_input

    setup_superadmin(email=email, password=password, org_name=org)
