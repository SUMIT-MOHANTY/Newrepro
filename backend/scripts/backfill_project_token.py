"""
Backfill script: Extract project_token from analysis_result JSON field
and populate the project_token column for all existing documents.

Run: python backfill_project_token.py
"""
import sys
import os
import json
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Document

def extract_project_token(analysis_result):
    """Extract project_token from analysis_result JSON string."""
    if not analysis_result:
        return None
    
    try:
        parsed = json.loads(analysis_result)
        if not isinstance(parsed, dict):
            return None
        
        # Try direct key first
        token = parsed.get("project_token")
        if token and isinstance(token, str) and token.strip():
            return token.strip()
        
        # Try nested projectMeta
        project_meta = parsed.get("projectMeta") or {}
        token = project_meta.get("project_token")
        if token and isinstance(token, str) and token.strip():
            return token.strip()
        
        # Try governanceContext
        governance_context = parsed.get("governanceContext") or {}
        token = governance_context.get("project_token")
        if token and isinstance(token, str) and token.strip():
            return token.strip()
        
        return None
    except (json.JSONDecodeError, TypeError, ValueError):
        # Try regex fallback for malformed JSON
        match = re.search(r'"project_token"\s*:\s*"([^"]+)"', str(analysis_result))
        if match:
            return match.group(1)
        return None

def backfill():
    db = SessionLocal()
    try:
        # Get all documents where project_token is null
        docs = db.query(Document).filter(
            Document.project_token.is_(None)
        ).all()
        
        print(f"Found {len(docs)} documents without project_token.")
        updated_count = 0
        
        for doc in docs:
            token = extract_project_token(doc.analysis_result)
            if token:
                doc.project_token = token
                db.add(doc)
                updated_count += 1
                if updated_count % 10 == 0:
                    db.flush()
                    print(f"  Processed {updated_count}/{len(docs)}...")
        
        db.commit()
        print(f"\n✅ Successfully backfilled {updated_count} documents.")
        print(f"   {len(docs) - updated_count} documents still have null project_token (no token found in analysis_result).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    backfill()
