"""
Script to clear all database tables except user login credentials.
Preserves: users table (email, hashed_password, is_active, etc.)
Clears: all other tables
"""
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import (
    PasswordReset, OrganizationRole, OrganizationRolePermission,
    UserOrganizationRole, OrganizationInvite, OAuthClient,
    OAuthAuthorizationCode, OrganizationPluginConnection,
    OrganizationSSOSetting, AgentCredential, Agent,
    OrganizationAgentQuota, OrganizationAgentMapping,
    Document, GovernanceResponse, GovernanceQuestion,
    GovernanceQuestionOption, Task, AgentMessage
)


def clear_database_except_users():
    """Clear all tables except users table"""
    db: Session = SessionLocal()
    
    try:
        print("Starting database cleanup...")
        print("=" * 60)
        
        # Order matters due to foreign key constraints
        # Delete in reverse dependency order
        
        tables_to_clear = [
            (AgentMessage, "Agent Messages"),
            (Task, "Tasks"),
            (GovernanceQuestionOption, "Governance Question Options"),
            (GovernanceQuestion, "Governance Questions"),
            (GovernanceResponse, "Governance Responses"),
            (Document, "Documents"),
            (OrganizationAgentMapping, "Organization Agent Mappings"),
            (Agent, "Agents"),
            (OrganizationAgentQuota, "Organization Agent Quotas"),
            (AgentCredential, "Agent Credentials"),
            (OrganizationSSOSetting, "Organization SSO Settings"),
            (OrganizationPluginConnection, "Organization Plugin Connections"),
            (OAuthAuthorizationCode, "OAuth Authorization Codes"),
            (OAuthClient, "OAuth Clients"),
            (OrganizationInvite, "Organization Invites"),
            (UserOrganizationRole, "User Organization Roles"),
            (OrganizationRolePermission, "Organization Role Permissions"),
            (OrganizationRole, "Organization Roles"),
            (PasswordReset, "Password Resets"),
        ]
        
        total_deleted = 0
        
        for model, name in tables_to_clear:
            count = db.query(model).count()
            if count > 0:
                db.query(model).delete()
                print(f"✓ Cleared {count} records from {name}")
                total_deleted += count
            else:
                print(f"  {name}: already empty")
        
        db.commit()
        
        print("=" * 60)
        print(f"✓ Database cleanup complete!")
        print(f"  Total records deleted: {total_deleted}")
        
        # Import User model to check count
        from models import User
        user_count = db.query(User).count()
        print(f"  User accounts preserved: {user_count}")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error during cleanup: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    print("\n" + "=" * 60)
    print("DATABASE CLEANUP SCRIPT")
    print("=" * 60)
    print("This will DELETE all data except user login credentials.")
    print("User accounts (email, password, etc.) will be preserved.")
    print("=" * 60)
    
    response = input("\nAre you sure you want to continue? (yes/no): ").strip().lower()
    
    if response == "yes":
        clear_database_except_users()
    else:
        print("\n✗ Operation cancelled.")
        sys.exit(0)
