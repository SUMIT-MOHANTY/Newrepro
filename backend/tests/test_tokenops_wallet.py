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

from sqlalchemy import event

@pytest.fixture(scope="function")
def session():
    """Provides a fresh in-memory SQLite database per test."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def do_begin(conn):
        conn.exec_driver_sql("BEGIN")

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


# ── F9: ATOMIC IDEMPOTENCY CONCURRENCY TESTS ─────────────────────────────────

def test_f9_concurrent_idempotency_race(tmp_path):
    """
    F9 Regression Test:
    Dispatches 10 concurrent threads attempting the exact same purchase with identical request_id.
    Guarantees:
      1. Exactly 1 request executes the financial operation.
      2. 9 concurrent duplicates cleanly return the idempotent state without exceptions.
      3. Exactly one financial balance mutation occurs (purchased +500).
      4. Exactly one ledger entry exists for this request_id.
      5. Exactly one idempotency record exists.
      6. No IntegrityError escapes as an unhandled error or HTTP 500.
    """
    import concurrent.futures
    import threading

    db_file = str(tmp_path / "test_idemp_concurrency.db")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"timeout": 30, "check_same_thread": False})
    
    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def do_begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine)

    org_name = "ConcurrentOrg"
    setup_db = SessionFactory()
    setup_org_wallet(setup_db, org_name, purchased=1000, remaining=1000, reserved=1000)
    setup_db.close()
    
    shared_request_id = str(uuid.uuid4())
    results = []
    errors = []
    lock = threading.Lock()

    def run_purchase():
        db = SessionFactory()
        try:
            org_repo = OrganizationWalletRepository(db)
            user_repo = UserWalletRepository(db)
            ledger_repo = LedgerRepository(db)
            idemp_repo = IdempotencyRepository(db)
            validation = ValidationService(org_repo, user_repo)
            ledger = LedgerService(ledger_repo)
            idemp = IdempotencyService(idemp_repo)
            ws = WalletService(db, org_repo, user_repo, validation, ledger, idemp)
            
            res = ws.purchase_tokens(
                organization_name=org_name,
                amount=500,
                request_id=shared_request_id,
                remarks="Concurrent test"
            )
            with lock:
                results.append(res)
        except Exception as e:
            with lock:
                errors.append(e)
        finally:
            db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(run_purchase) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    # 1. Zero unhandled errors or IntegrityErrors
    assert len(errors) == 0, f"Unexpected errors during concurrent idempotency: {errors}"
    assert len(results) == 10

    # 2. Exactly ONE financial mutation was committed (1000 + 500 = 1500)
    verify_db = SessionFactory()
    wallet = verify_db.query(OrganizationWallet).filter_by(organization_name=org_name).first()
    assert wallet.purchased_tokens == 1500
    assert wallet.remaining_tokens == 1500

    # 3. Exactly ONE ledger entry exists
    ledger_entries = verify_db.query(TokenTransactionLedger).filter_by(reference_id=shared_request_id).all()
    assert len(ledger_entries) == 1
    assert ledger_entries[0].token_delta == 500

    # 4. Exactly ONE idempotency record exists
    idemp_keys = verify_db.query(IdempotencyKey).filter_by(request_id=shared_request_id).all()
    assert len(idemp_keys) == 1
    assert idemp_keys[0].status == "COMPLETED"
    verify_db.close()


# ── F10: FINANCIAL AUDIT TRANSACTION ATOMICITY & ROLLBACK TESTS ──────────────

from tokenops.services.admin.admin_wallet_service import AdminWalletService
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.services.org_admin.org_wallet_service import OrgWalletService
from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.models.audit import AdminAuditLog
from unittest.mock import MagicMock


def test_f10_purchase_tokens_audit_failure_rollback(session: Session, wallet_service: WalletService):
    """
    F10 Regression Test:
    When AdminAuditService.log_action raises an exception during purchase_tokens,
    the entire transaction rolls back atomically (wallet balance, ledger, and audit log).
    """
    org_name = "AuditFailOrg"
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=1000)
    
    mock_audit = AdminAuditService(session)
    mock_audit.log_action = MagicMock(side_effect=RuntimeError("Audit database disk full"))
    
    org_repo = OrganizationWalletRepository(session)
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    
    admin_wallet_svc = AdminWalletService(session, wallet_service, mock_audit, org_repo, pricing_service)
    
    with pytest.raises(RuntimeError, match="Audit database disk full"):
        admin_wallet_svc.purchase_tokens(admin_user_id=1, organization_name=org_name, token_amount=500)

    # Invariant assertions: wallet unchanged, zero ledger entries, zero audit log entries
    wallet = session.query(OrganizationWallet).filter_by(organization_name=org_name).first()
    assert wallet.purchased_tokens == 1000
    assert wallet.remaining_tokens == 1000
    assert session.query(TokenTransactionLedger).count() == 0
    assert session.query(AdminAuditLog).count() == 0


def test_f10_allocate_tokens_audit_failure_rollback(session: Session, wallet_service: WalletService):
    """
    F10 Regression Test:
    When OrgAuditService.log_action raises an exception during allocate_tokens,
    the entire transaction rolls back atomically (org reserve, user wallet, ledger, and audit log).
    """
    org_name = "AuditFailOrg2"
    user_id = 1
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=1000)
    setup_user_wallet(session, user_id, org_name, allocated=0, consumed=0, remaining=0)
    
    mock_audit = OrgAuditService(session)
    mock_audit.log_action = MagicMock(side_effect=RuntimeError("Audit database error"))
    
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    
    org_wallet_svc = OrgWalletService(session, wallet_service, mock_audit, org_repo, user_repo, pricing_service)
    
    with pytest.raises(RuntimeError, match="Audit database error"):
        org_wallet_svc.allocate_tokens(
            admin_user_id=99,
            organization_name=org_name,
            request_id="req-alloc-fail",
            user_id=user_id,
            token_amount=200
        )

    # Invariant assertions: org reserve & user wallet unchanged, zero ledger, zero audit log
    org_wallet = session.query(OrganizationWallet).filter_by(organization_name=org_name).first()
    user_wallet = session.query(UserTokenWallet).filter_by(user_id=user_id, organization_name=org_name).first()
    assert org_wallet.reserved_tokens == 1000
    assert user_wallet.remaining_tokens == 0
    assert user_wallet.allocated_tokens == 0
    assert session.query(TokenTransactionLedger).count() == 0
    assert session.query(AdminAuditLog).count() == 0


def test_f10_reallocate_tokens_audit_failure_rollback(session: Session, wallet_service: WalletService):
    """
    F10 Regression Test:
    When OrgAuditService.log_action raises an exception during reallocate_tokens,
    the entire transaction rolls back atomically (both user wallets, ledger, and audit log).
    """
    org_name = "AuditFailOrg3"
    user_1 = 1
    user_2 = 2
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=800)
    setup_user_wallet(session, user_1, org_name, allocated=200, consumed=0, remaining=200)
    setup_user_wallet(session, user_2, org_name, allocated=0, consumed=0, remaining=0)
    
    mock_audit = OrgAuditService(session)
    mock_audit.log_action = MagicMock(side_effect=RuntimeError("Audit database error"))
    
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    
    org_wallet_svc = OrgWalletService(session, wallet_service, mock_audit, org_repo, user_repo, pricing_service)
    
    with pytest.raises(RuntimeError, match="Audit database error"):
        org_wallet_svc.reallocate_tokens(
            admin_user_id=99,
            organization_name=org_name,
            request_id="req-realloc-fail",
            source_user_id=user_1,
            destination_user_id=user_2,
            token_amount=100
        )

    # Invariant assertions: source & target user balances unchanged, zero ledger, zero audit log
    u1 = session.query(UserTokenWallet).filter_by(user_id=user_1, organization_name=org_name).first()
    u2 = session.query(UserTokenWallet).filter_by(user_id=user_2, organization_name=org_name).first()
    assert u1.remaining_tokens == 200
    assert u2.remaining_tokens == 0
    assert session.query(TokenTransactionLedger).count() == 0
    assert session.query(AdminAuditLog).count() == 0


def test_f10_revoke_tokens_audit_failure_rollback(session: Session, wallet_service: WalletService):
    """
    F10 Regression Test:
    When OrgAuditService.log_action raises an exception during revoke_tokens,
    the entire transaction rolls back atomically (user wallet, org reserve, ledger, and audit log).
    """
    org_name = "AuditFailOrg4"
    user_id = 1
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=800)
    setup_user_wallet(session, user_id, org_name, allocated=200, consumed=0, remaining=200)
    
    mock_audit = OrgAuditService(session)
    mock_audit.log_action = MagicMock(side_effect=RuntimeError("Audit database error"))
    
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    
    org_wallet_svc = OrgWalletService(session, wallet_service, mock_audit, org_repo, user_repo, pricing_service)
    
    with pytest.raises(RuntimeError, match="Audit database error"):
        org_wallet_svc.revoke_tokens(
            admin_user_id=99,
            organization_name=org_name,
            request_id="req-revoke-fail",
            user_id=user_id,
            token_amount=100
        )

    # Invariant assertions: user wallet & org reserve unchanged, zero ledger, zero audit log
    u = session.query(UserTokenWallet).filter_by(user_id=user_id, organization_name=org_name).first()
    org_w = session.query(OrganizationWallet).filter_by(organization_name=org_name).first()
    assert u.remaining_tokens == 200
    assert org_w.reserved_tokens == 800
    assert session.query(TokenTransactionLedger).count() == 0
    assert session.query(AdminAuditLog).count() == 0


def test_f10_successful_operation_commits_wallet_ledger_audit_together(session: Session, wallet_service: WalletService):
    """
    F10 Regression Test:
    Proves that on success, wallet mutation, ledger entry, and audit log commit together atomically.
    """
    org_name = "SuccessOrg"
    user_id = 1
    setup_org_wallet(session, org_name, purchased=1000, remaining=1000, reserved=1000)
    setup_user_wallet(session, user_id, org_name, allocated=0, consumed=0, remaining=0)
    
    admin_audit = AdminAuditService(session)
    org_audit = OrgAuditService(session)
    
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    
    admin_wallet_svc = AdminWalletService(session, wallet_service, admin_audit, org_repo, pricing_service)
    org_wallet_svc = OrgWalletService(session, wallet_service, org_audit, org_repo, user_repo, pricing_service)
    
    # 1. Purchase
    admin_wallet_svc.purchase_tokens(admin_user_id=1, organization_name=org_name, token_amount=500, remarks="Batch top-up")
    
    # 2. Allocate
    org_wallet_svc.allocate_tokens(admin_user_id=99, organization_name=org_name, request_id="alloc-succ", user_id=user_id, token_amount=200, remarks="Sprint quota")
    
    # Invariant assertions: wallet balances correct
    org_w = session.query(OrganizationWallet).filter_by(organization_name=org_name).first()
    u_w = session.query(UserTokenWallet).filter_by(user_id=user_id, organization_name=org_name).first()
    assert org_w.purchased_tokens == 1500
    assert org_w.reserved_tokens == 1300
    assert u_w.allocated_tokens == 200
    assert u_w.remaining_tokens == 200
    
    # Exactly 2 ledger entries
    ledger_entries = session.query(TokenTransactionLedger).all()
    assert len(ledger_entries) == 2
    assert ledger_entries[0].transaction_type == TransactionType.PURCHASE.value
    assert ledger_entries[1].transaction_type == TransactionType.ALLOCATION.value
    
    # Exactly 2 audit logs
    audit_logs = session.query(AdminAuditLog).all()
    assert len(audit_logs) == 2
    assert audit_logs[0].action == "PURCHASE_TOKENS"
    assert audit_logs[1].action == "ALLOCATE_TOKENS"
