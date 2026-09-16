"""
Migration script: Add 'user_token_quota_requests' table for member token quota top-up requests.
"""

import os
import sys
import logging

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect, text
from database import engine, Base
from tokenops.models.user_quota_request import UserTokenQuotaRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    logger.info("Starting migration: add_user_quota_requests...")
    inspector = inspect(engine)

    if "user_token_quota_requests" not in inspector.get_table_names():
        logger.info("Creating table 'user_token_quota_requests'...")
        UserTokenQuotaRequest.__table__.create(bind=engine, checkfirst=True)
        logger.info("Table 'user_token_quota_requests' created successfully.")
    else:
        logger.info("Table 'user_token_quota_requests' already exists.")

    logger.info("Migration add_user_quota_requests completed successfully.")

if __name__ == "__main__":
    run_migration()
