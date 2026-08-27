import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from database import Base
import uuid

# Models
from tokenops.models.token_wallet import OrganizationWallet, UserTokenWallet
from tokenops.models.idempotency import IdempotencyKey
from tokenops.models.ledger import TokenTransactionLedger, TransactionType
from tokenops.models.pricing import ModelPricing

# Repositories
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.repositories.ledger import LedgerRepository
from tokenops.repositories.idempotency import IdempotencyRepository
from tokenops.repositories.pricing import PricingRepository
from tokenops.repositories.usage_summary import UsageSummaryRepository

# Services
from tokenops.services.wallet_service import WalletService
from tokenops.services.validation_service import ValidationService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.services.pricing_service import PricingService
from tokenops.services.usage_summary_service import UsageSummaryService

@pytest.fixture(scope="function")
def session():
    """Provides a fresh in-memory SQLite database per test."""
    engine = create_engine("sqlite:///:memory:")
    # Enable WAL and foreign keys for SQLite
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        
    import models # import all base models to ensure Users table is known to Base.metadata
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # We must yield the session to the test
    yield session
    
    session.close()

@pytest.fixture
def wallet_service(session: Session):
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    ledger_repo = LedgerRepository(session)
    idemp_repo = IdempotencyRepository(session)
    
    validation = ValidationService(org_repo, user_repo)
    ledger = LedgerService(ledger_repo)
    idemp = IdempotencyService(idemp_repo)
    
    return WalletService(session, org_repo, user_repo, validation, ledger, idemp)

def setup_org_wallet(session: Session, org_name: str, purchased=0, remaining=0, reserved=0):
    wallet = OrganizationWallet(organization_name=org_name, purchased_tokens=purchased, remaining_tokens=remaining, reserved_tokens=reserved)
    session.add(wallet)
    session.commit()
    return wallet

def setup_user_wallet(session: Session, user_id: int, org_name: str, allocated=0, consumed=0, remaining=0):
    from models import User
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        user = User(id=user_id, email=f"test{user_id}@test.com", hashed_password="dummy")
        session.add(user)
        session.commit()
        
    wallet = UserTokenWallet(user_id=user_id, organization_name=org_name, allocated_tokens=allocated, consumed_tokens=consumed, remaining_tokens=remaining)
    session.add(wallet)
    session.commit()
    return wallet

def test_purchase_tokens(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    setup_org_wallet(session, org_name)
    
    req_id = str(uuid.uuid4())
    state = wallet_service.purchase_tokens(org_name, 1000, req_id)
    
    assert state.remaining == 1000
    assert state.reserved == 1000
    
    ledger_entry = session.query(TokenTransactionLedger).first()
    assert ledger_entry.transaction_type == TransactionType.PURCHASE.value
    assert ledger_entry.token_delta == 1000
    assert ledger_entry.balance_after == 1000

def test_allocate_tokens(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    user_id = 1
    # reserve = purchased - allocated_to_users (0) = 1000
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=1000)
    setup_user_wallet(session, user_id, org_name, allocated=0, consumed=0, remaining=0)
    
    req_id = str(uuid.uuid4())
    state = wallet_service.allocate_tokens(user_id, org_name, 200, req_id)
    
    assert state.allocated == 200
    assert state.remaining == 200
    
    ledger_entry = session.query(TokenTransactionLedger).first()
    assert ledger_entry.transaction_type == TransactionType.ALLOCATION.value
    assert ledger_entry.token_delta == 200
    # P0-7 fix: balance_after represents USER wallet remaining after allocation (0 + 200 = 200)
    assert ledger_entry.balance_after == 200

def test_reallocate_tokens(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    user_1 = 1
    user_2 = 2
    # reserve = purchased - allocated_to_users (200) = 800
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=800)
    setup_user_wallet(session, user_1, org_name, allocated=200, consumed=0, remaining=200)
    setup_user_wallet(session, user_2, org_name, allocated=0, consumed=0, remaining=0)
    
    req_id = str(uuid.uuid4())
    state = wallet_service.reallocate_tokens(user_1, user_2, org_name, 100, req_id)
    
    assert state.allocated == 100
    assert state.remaining == 100
    
    txs = session.query(TokenTransactionLedger).all()
    assert len(txs) == 2
    assert txs[0].transaction_type == TransactionType.REALLOCATION.value
    assert txs[0].token_delta == -100
    assert txs[1].token_delta == 100
    # P0-7 fix: balance_after represents the user wallet being operated on.
    # Out leg: from_user remaining before = 200, after = 100.
    assert txs[0].balance_after == 100
    # In leg: to_user remaining before = 0, after = 100.
    assert txs[1].balance_after == 100

def test_revoke_tokens(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    user_id = 1
    # reserve = purchased - allocated_to_users (200) = 800
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=800)
    setup_user_wallet(session, user_id, org_name, allocated=200, consumed=0, remaining=200)
    
    req_id = str(uuid.uuid4())
    state = wallet_service.revoke_tokens(user_id, org_name, 150, req_id)
    
    assert state.allocated == 50
    assert state.remaining == 50
    
    ledger_entry = session.query(TokenTransactionLedger).first()
    assert ledger_entry.transaction_type == TransactionType.REVOCATION.value
    assert ledger_entry.token_delta == -150
    # P0-7 fix: balance_after represents USER wallet remaining after revoke (200 - 150 = 50)
    assert ledger_entry.balance_after == 50

def test_idempotency(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    setup_org_wallet(session, org_name)
    
    req_id = str(uuid.uuid4())
    state1 = wallet_service.purchase_tokens(org_name, 1000, req_id)
    state2 = wallet_service.purchase_tokens(org_name, 1000, req_id) # Duplicate
    
    assert state1.remaining == 1000
    assert state2.remaining == 1000 # Should not have added another 1000
    
    ledger_entries = session.query(TokenTransactionLedger).all()
    assert len(ledger_entries) == 1

def test_rollback_on_failure(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    user_id = 1
    # Valid setup: purchased=100, reserved=100
    setup_org_wallet(session, org_name, purchased=100, remaining=100, reserved=100)
    setup_user_wallet(session, user_id, org_name)
    
    req_id = str(uuid.uuid4())

    # Try to allocate more than available
    with pytest.raises(ValueError, match="Insufficient available tokens"):
        wallet_service.allocate_tokens(user_id, org_name, 1000, req_id)
        
    # Idempotency key should NOT be present (rolled back)
    status = session.execute(
        text("SELECT status FROM idempotency_keys WHERE request_id = :req"),
        {"req": req_id}
    ).scalar_one_or_none()
    assert status is None

    # Ledger should be empty
    assert session.query(TokenTransactionLedger).count() == 0

def test_running_balance(session: Session, wallet_service: WalletService):
    org_name = "TestOrg"
    user_id = 1
    setup_org_wallet(session, org_name)
    setup_user_wallet(session, user_id, org_name)
    
    # Purchase 1000
    wallet_service.purchase_tokens(org_name, 1000)
    
    # Allocate 200
    wallet_service.allocate_tokens(user_id, org_name, 200)
    
    # Revoke 50
    wallet_service.revoke_tokens(user_id, org_name, 50)
    
    entries = session.query(TokenTransactionLedger).order_by(TokenTransactionLedger.id.asc()).all()
    assert len(entries) == 3
    # Entry 0: PURCHASE — org remaining 0 + 1000 = 1000
    assert entries[0].balance_after == 1000
    # Entry 1: ALLOCATION — user remaining 0 + 200 = 200 (P0-7 fix)
    assert entries[1].balance_after == 200
    # Entry 2: REVOCATION — user remaining 200 - 50 = 150 (P0-7 fix)
    assert entries[2].balance_after == 150
