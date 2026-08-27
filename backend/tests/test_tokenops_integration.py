import pytest
import uuid
import time
import threading
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from tokenops.services.tokenops_orchestrator import TokenOpsOrchestrator
from tokenops.models.token_wallet import OrganizationWallet, UserOrganization, UserTokenWallet
from tokenops.models.pricing import ModelPricing
from tokenops.models.summary import OrganizationUsageSummary, UserUsageSummary
from models import User, AIUsageLog
from tokenops.models.ledger import TokenTransactionLedger
from tokenops.models.organization import Organization, LegacyOrganizationIdentifier

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()

def setup_base_data(db):
    o1 = Organization(id=str(uuid.uuid4()), name="test_org")
    l1 = LegacyOrganizationIdentifier(organization_id=o1.id, legacy_name="test_org")
    
    o2 = Organization(id=str(uuid.uuid4()), name="payg_org")
    l2 = LegacyOrganizationIdentifier(organization_id=o2.id, legacy_name="payg_org")

    o3 = Organization(id=str(uuid.uuid4()), name="blocked_org")
    l3 = LegacyOrganizationIdentifier(organization_id=o3.id, legacy_name="blocked_org")

    o4 = Organization(id=str(uuid.uuid4()), name="exhaust_org")
    l4 = LegacyOrganizationIdentifier(organization_id=o4.id, legacy_name="exhaust_org")

    db.add_all([o1, l1, o2, l2, o3, l3, o4, l4])
    
    org = OrganizationWallet(
        organization_name="test_org",
        purchased_tokens=1000,
        remaining_tokens=1000,
        reserved_tokens=1000,
        payg_enabled=False,
        is_blocked=False
    )
    
    org_payg = OrganizationWallet(
        organization_name="payg_org",
        purchased_tokens=0,
        remaining_tokens=0,
        reserved_tokens=0,
        payg_enabled=True,
        is_blocked=False
    )
    
    org_blocked = OrganizationWallet(
        organization_name="blocked_org",
        purchased_tokens=1000,
        remaining_tokens=1000,
        reserved_tokens=1000,
        is_blocked=True
    )
    
    org_exhaust = OrganizationWallet(
        organization_name="exhaust_org",
        purchased_tokens=1000,
        remaining_tokens=1000,
        reserved_tokens=1000,
        payg_enabled=False
    )
    
    user1 = User(id=1, email="user1@test.com", organization_name="test_org")
    user2 = User(id=2, email="user2@test.com", organization_name="payg_org")
    user3 = User(id=3, email="user3@test.com", organization_name="blocked_org")
    user4 = User(id=4, email="user4@test.com", organization_name="exhaust_org")
    
    db.add_all([org, org_payg, org_blocked, org_exhaust])
    db.add_all([user1, user2, user3, user4])
    
    m1 = UserOrganization(user_id=1, organization_name="test_org")
    m2 = UserOrganization(user_id=2, organization_name="payg_org")
    m3 = UserOrganization(user_id=3, organization_name="blocked_org")
    m4 = UserOrganization(user_id=4, organization_name="exhaust_org")
    db.add_all([m1, m2, m3, m4])
    
    uw1 = UserTokenWallet(user_id=1, organization_name="test_org", allocated_tokens=1000, consumed_tokens=0, remaining_tokens=1000)
    uw3 = UserTokenWallet(user_id=3, organization_name="blocked_org", allocated_tokens=1000, consumed_tokens=0, remaining_tokens=1000)
    uw4 = UserTokenWallet(user_id=4, organization_name="exhaust_org", allocated_tokens=1000, consumed_tokens=1000, remaining_tokens=0)
    db.add_all([uw1, uw3, uw4])
    
    db.commit()
    return db

def test_prepaid_success(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    orchestrator.pre_execute(user_id=1, organization_name="test_org")
    
    req_id = str(uuid.uuid4())
    orchestrator.post_execute(
        user_id=1,
        organization_name="test_org",
        model_name="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        request_id=req_id
    )
    
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=1, organization_name="test_org").first()
    assert u_wallet.consumed_tokens == 150
    assert u_wallet.remaining_tokens == 850
    
    ledger = session.query(TokenTransactionLedger).filter_by(reference_id=req_id).first()
    assert ledger is not None
    assert ledger.token_delta == -150
    assert ledger.balance_after == 850

def test_payg_success(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    orchestrator.pre_execute(user_id=2, organization_name="payg_org")
    req_id = str(uuid.uuid4())
    orchestrator.post_execute(
        user_id=2,
        organization_name="payg_org",
        model_name="test-model",
        prompt_tokens=200,
        completion_tokens=100,
        request_id=req_id
    )
    
    usage = session.query(OrganizationUsageSummary).filter_by(organization_name="payg_org").first()
    assert usage is not None
    assert usage.total_tokens == 300
    
    ledger = session.query(TokenTransactionLedger).filter_by(reference_id=req_id).first()
    assert ledger is not None
    assert ledger.transaction_type == "PAYG_USAGE"
    assert ledger.token_delta == -300

def test_403_invalid_org(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    with pytest.raises(HTTPException) as exc:
        orchestrator.pre_execute(user_id=1, organization_name="invalid_org")
    assert exc.value.status_code == 404 or exc.value.status_code == 403

def test_403_blocked_user(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    uw = session.query(UserTokenWallet).filter_by(user_id=1, organization_name="test_org").first()
    uw.is_blocked = True
    session.commit()
    
    with pytest.raises(HTTPException) as exc:
        orchestrator.pre_execute(user_id=1, organization_name="test_org")
    assert exc.value.status_code == 403
    assert exc.value.detail == "USER_BLOCKED"

def test_403_blocked_org(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    with pytest.raises(HTTPException) as exc:
        orchestrator.pre_execute(user_id=3, organization_name="blocked_org")
    assert exc.value.status_code == 403
    assert exc.value.detail == "ORGANIZATION_BLOCKED"

def test_402_exhausted(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    with pytest.raises(HTTPException) as exc:
        orchestrator.pre_execute(user_id=4, organization_name="exhaust_org")
    assert exc.value.status_code == 402
    assert exc.value.detail == "TOKEN_EXHAUSTED"

def test_streaming_success(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    orchestrator.pre_execute(user_id=1, organization_name="test_org")
    req_id = str(uuid.uuid4())
    orchestrator.post_execute(
        user_id=1,
        organization_name="test_org",
        model_name="test-model",
        prompt_tokens=10,
        completion_tokens=20,
        request_id=req_id
    )
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=1, organization_name="test_org").first()
    assert u_wallet.consumed_tokens == 30

def test_stream_ending_at_0(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    orchestrator.pre_execute(user_id=1, organization_name="test_org")
    orchestrator.post_execute(
        user_id=1,
        organization_name="test_org",
        model_name="test-model",
        prompt_tokens=500,
        completion_tokens=500,
    )
    
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=1, organization_name="test_org").first()
    assert u_wallet.remaining_tokens == 0
    
    with pytest.raises(HTTPException) as exc:
        orchestrator.pre_execute(user_id=1, organization_name="test_org")
    assert exc.value.status_code == 402

def test_duplicate_request(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    req_id = str(uuid.uuid4())
    
    orchestrator.post_execute(
        user_id=1,
        organization_name="test_org",
        model_name="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        request_id=req_id
    )
    
    orchestrator.post_execute(
        user_id=1,
        organization_name="test_org",
        model_name="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        request_id=req_id
    )
    
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=1, organization_name="test_org").first()
    assert u_wallet.consumed_tokens == 150

def test_unknown_usage(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    
    req_id = str(uuid.uuid4())
    orchestrator.post_execute(
        user_id=1,
        organization_name="test_org",
        model_name="test-model",
        prompt_tokens=None,
        completion_tokens=None,
        request_id=req_id
    )
    
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=1, organization_name="test_org").first()
    assert u_wallet.consumed_tokens == 0
    
    log = session.query(AIUsageLog).filter_by(project_token="test_org").order_by(AIUsageLog.id.desc()).first()
    assert log is not None
    assert log.usage_status == "UNKNOWN"
    assert log.prompt_tokens == 0

def test_prepaid_full_accounting_lifecycle(session):
    setup_base_data(session)
    orchestrator = TokenOpsOrchestrator.create(session)
    wallet_service = orchestrator.wallet

    # Create new dedicated clean organization
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="lifecycle_org")
    alias = LegacyOrganizationIdentifier(organization_id=org_id, legacy_name="lifecycle_org")
    user = User(id=100, email="lifecycle_user@test.com", organization_name="lifecycle_org")
    membership = UserOrganization(user_id=100, organization_name="lifecycle_org", is_active=True)
    user_wallet = UserTokenWallet(user_id=100, organization_name="lifecycle_org", allocated_tokens=0, consumed_tokens=0, remaining_tokens=0)
    session.add_all([org, alias, user, membership, user_wallet])
    session.commit()

    # Step 1: Super Admin purchases 5000 tokens for Organization lifecycle_org
    purchase_req_id = f"purch_{uuid.uuid4()}"
    wallet_service.purchase_tokens(
        organization_name="lifecycle_org",
        amount=5000,
        request_id=purchase_req_id,
        remarks="Initial Purchase 5000"
    )

    org_wallet = session.query(OrganizationWallet).filter_by(organization_name="lifecycle_org").first()
    assert org_wallet.purchased_tokens == 5000
    assert org_wallet.reserved_tokens == 5000
    assert org_wallet.remaining_tokens == 5000

    purchase_ledger = session.query(TokenTransactionLedger).filter_by(reference_id=purchase_req_id).first()
    assert purchase_ledger is not None
    assert purchase_ledger.transaction_type == "PURCHASE"
    assert purchase_ledger.token_delta == 5000
    assert purchase_ledger.balance_after == 5000

    # Step 2: Org Admin allocates 2000 tokens to User 100
    alloc_req_id = f"alloc_{uuid.uuid4()}"
    wallet_service.allocate_tokens(
        user_id=100,
        organization_name="lifecycle_org",
        amount=2000,
        request_id=alloc_req_id
    )

    org_wallet = session.query(OrganizationWallet).filter_by(organization_name="lifecycle_org").first()
    assert org_wallet.reserved_tokens == 3000  # 5000 - 2000

    u_wallet = session.query(UserTokenWallet).filter_by(user_id=100, organization_name="lifecycle_org").first()
    assert u_wallet.allocated_tokens == 2000
    assert u_wallet.consumed_tokens == 0
    assert u_wallet.remaining_tokens == 2000

    alloc_ledger = session.query(TokenTransactionLedger).filter_by(reference_id=alloc_req_id).first()
    assert alloc_ledger is not None
    assert alloc_ledger.transaction_type == "ALLOCATION"
    assert alloc_ledger.token_delta == 2000
    assert alloc_ledger.balance_after == 2000

    # Step 3: User 100 consumes 350 tokens via AI call
    ai_req_id = str(uuid.uuid4())
    orchestrator.pre_execute(user_id=100, organization_name="lifecycle_org")
    orchestrator.post_execute(
        user_id=100,
        organization_name="lifecycle_org",
        model_name="test-model",
        prompt_tokens=200,
        completion_tokens=150,
        request_id=ai_req_id
    )

    u_wallet = session.query(UserTokenWallet).filter_by(user_id=100, organization_name="lifecycle_org").first()
    assert u_wallet.allocated_tokens == 2000
    assert u_wallet.consumed_tokens == 350
    assert u_wallet.remaining_tokens == 1650  # 2000 - 350

    # Org reserve is unaffected by consumption
    org_wallet = session.query(OrganizationWallet).filter_by(organization_name="lifecycle_org").first()
    assert org_wallet.reserved_tokens == 3000

    ai_ledger = session.query(TokenTransactionLedger).filter_by(reference_id=ai_req_id).first()
    assert ai_ledger is not None
    assert ai_ledger.transaction_type == "AI_CONSUMPTION"
    assert ai_ledger.token_delta == -350
    assert ai_ledger.balance_after == 1650

    # Step 4: Org Admin revokes 500 tokens from User 100
    revoke_req_id = f"rev_{uuid.uuid4()}"
    wallet_service.revoke_tokens(
        user_id=100,
        organization_name="lifecycle_org",
        amount=500,
        request_id=revoke_req_id
    )

    u_wallet = session.query(UserTokenWallet).filter_by(user_id=100, organization_name="lifecycle_org").first()
    assert u_wallet.allocated_tokens == 1500  # 2000 - 500
    assert u_wallet.consumed_tokens == 350
    assert u_wallet.remaining_tokens == 1150  # 1500 - 350
    assert u_wallet.remaining_tokens == u_wallet.allocated_tokens - u_wallet.consumed_tokens

    org_wallet = session.query(OrganizationWallet).filter_by(organization_name="lifecycle_org").first()
    assert org_wallet.reserved_tokens == 3500  # 3000 + 500

    rev_ledger = session.query(TokenTransactionLedger).filter_by(reference_id=revoke_req_id).first()
    assert rev_ledger is not None
    assert rev_ledger.transaction_type == "REVOCATION"
    assert rev_ledger.token_delta == -500
    assert rev_ledger.balance_after == 1150


# ── F5 Fix Regression Test: Case-Insensitive UserTokenWallet Lookup ─────────
def test_f5_case_insensitive_user_wallet_lookup(session):
    orchestrator = TokenOpsOrchestrator.create(session)

    # 1. Setup organization with mixed-case canonical name "Acme Corp"
    org = Organization(id=str(uuid.uuid4()), name="Acme Corp")
    legacy = LegacyOrganizationIdentifier(organization_id=org.id, legacy_name="Acme Corp")
    wallet = OrganizationWallet(
        organization_name="Acme Corp",
        purchased_tokens=5000,
        remaining_tokens=5000,
        reserved_tokens=4000,
        payg_enabled=False
    )
    user = User(id=200, email="acme_user@test.com", organization_name="Acme Corp")
    membership = UserOrganization(user_id=200, organization_name="Acme Corp", is_active=True)
    user_wallet = UserTokenWallet(
        user_id=200,
        organization_name="Acme Corp",
        allocated_tokens=1000,
        consumed_tokens=0,
        remaining_tokens=1000,
        is_blocked=False
    )

    session.add_all([org, legacy, wallet, user, membership, user_wallet])
    session.commit()

    # 2. Test pre_execute with UPPERCASE "ACME CORP"
    orchestrator.pre_execute(user_id=200, organization_name="ACME CORP")

    # 3. Test post_execute with lowercase "acme corp"
    req1 = str(uuid.uuid4())
    orchestrator.post_execute(
        user_id=200,
        organization_name="acme corp",
        model_name="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        request_id=req1
    )

    # Verify consumption recorded on the user wallet
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=200).first()
    assert u_wallet.organization_name == "Acme Corp"  # Preserved original stored casing
    assert u_wallet.consumed_tokens == 150
    assert u_wallet.remaining_tokens == 850

    # 4. Test pre_execute and post_execute with mixed case "aCmE cOrP"
    orchestrator.pre_execute(user_id=200, organization_name="aCmE cOrP")
    req2 = str(uuid.uuid4())
    orchestrator.post_execute(
        user_id=200,
        organization_name="aCmE cOrP",
        model_name="test-model",
        prompt_tokens=200,
        completion_tokens=100,
        request_id=req2
    )

    session.refresh(u_wallet)
    assert u_wallet.consumed_tokens == 450
    assert u_wallet.remaining_tokens == 550

    # 5. Verify UserWalletRepository case-insensitivity
    from tokenops.repositories.user_wallet import UserWalletRepository
    user_repo = UserWalletRepository(session)
    assert user_repo.get_user_wallet(200, "ACME CORP") is not None
    assert user_repo.get_user_wallet(200, "acme corp") is not None
    assert user_repo.get_membership(200, "ACME CORP") is not None
    assert user_repo.get_total_allocated("acme corp") == 1000


