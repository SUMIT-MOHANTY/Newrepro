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
    GovernanceQuestionOption, Task, AgentMessage,
    ChatMessage, UserProjectAssociation, HandoffToken,
    SharedDocument, SharedDocumentFile, SharedDocumentRecipient,
    SharedDocumentAccessLog, ShareProject,
    AgentTaskOwnership, ProjectCanonicalState,
    AgentExecutionCheckpoint, NXDuneSyncLog,
    BootstrapState
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
            (ChatMessage, "Chat Messages"),
            (SharedDocumentAccessLog, "Shared Document Access Logs"),
            (SharedDocumentRecipient, "Shared Document Recipients"),
            (SharedDocumentFile, "Shared Document Files"),
            (SharedDocument, "Shared Documents"),
            (ShareProject, "Share Projects"),
            (AgentTaskOwnership, "Agent Task Ownerships"),
            (AgentExecutionCheckpoint, "Agent Execution Checkpoints"),
            (NXDuneSyncLog, "NXDune Sync Logs"),
            (ProjectCanonicalState, "Project Canonical States"),
            (BootstrapState, "Bootstrap States"),
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
            (UserProjectAssociation, "User Project Associations"),
            (UserOrganizationRole, "User Organization Roles"),
            (OrganizationRolePermission, "Organization Role Permissions"),
            (OrganizationRole, "Organization Roles"),
            (PasswordReset, "Password Resets"),
            (HandoffToken, "Handoff Tokens"),
        ]
        
        total_deleted = 0
        
        for model, name in tables_to_clear:
            count = db.query(model).count()
            if count > 0:
                db.query(model).delete()
                print(f"[OK] Cleared {count} records from {name}")
                total_deleted += count
            else:
                print(f"  {name}: already empty")
        
        db.commit()
        
        print("=" * 60)
        print(f"[OK] Database cleanup complete!")
        print(f"  Total records deleted: {total_deleted}")
        
        # Import User model to check count
        from models import User
        user_count = db.query(User).count()
        print(f"  User accounts preserved: {user_count}")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error during cleanup: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    # Check if force/yes is passed as command line argument to bypass prompt
    force_run = False
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("--force", "-f", "yes", "force"):
        force_run = True
        
    if force_run:
        clear_database_except_users()
    else:
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
            print("\n[CANCELLED] Operation cancelled.")
            sys.exit(0)
