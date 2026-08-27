import pytest
import uuid
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base

from tokenops.models.token_wallet import OrganizationWallet, UserOrganization, UserTokenWallet
from tokenops.models.summary import OrganizationUsageSummary, UserUsageSummary
from tokenops.models.ledger import TokenTransactionLedger
from tokenops.models.audit import AdminAuditLog
from models import User, UserOrganizationRole, OrganizationRole

from tokenops.services.org_admin.org_audit_service import OrgAuditService
from tokenops.services.org_admin.org_wallet_service import OrgWalletService
from tokenops.services.org_admin.org_governance_service import OrgGovernanceService
from tokenops.services.org_admin.org_analytics_service import OrgAnalyticsService
from tokenops.services.wallet_service import WalletService
from tokenops.services.validation_service import ValidationService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.repositories.ledger import LedgerRepository
from tokenops.repositories.idempotency import IdempotencyRepository

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()

def setup_base_data(db):
    org = OrganizationWallet(organization_name="test_org", purchased_tokens=2000, reserved_tokens=2000, remaining_tokens=2000)
    user1 = User(id=1, email="admin@test.com")
    user2 = User(id=2, email="user@test.com")
    
    role_admin = OrganizationRole(id=1, organization_name="test_org", name="ORG_ADMIN")
    role_member = OrganizationRole(id=2, organization_name="test_org", name="MEMBER")
    
    m1 = UserOrganization(user_id=1, organization_name="test_org", is_active=True)
    m2 = UserOrganization(user_id=2, organization_name="test_org", is_active=True)
    
    rm1 = UserOrganizationRole(user_id=1, organization_name="test_org", role_id=1)
    rm2 = UserOrganizationRole(user_id=2, organization_name="test_org", role_id=2)
    
    uw1 = UserTokenWallet(user_id=1, organization_name="test_org", allocated_tokens=0, remaining_tokens=0)
    uw2 = UserTokenWallet(user_id=2, organization_name="test_org", allocated_tokens=0, remaining_tokens=0)
    
    org_summary = OrganizationUsageSummary(organization_name="test_org", total_tokens=100, request_count=5)
    user_summary = UserUsageSummary(user_id=2, organization_name="test_org", total_tokens=100, request_count=5)
    
    db.add_all([org, user1, user2, role_admin, role_member, m1, m2, rm1, rm2, uw1, uw2, org_summary, user_summary])
    db.commit()

from tokenops.repositories.pricing import PricingRepository
from tokenops.services.pricing_service import PricingService
from tokenops.models.organization import Organization, LegacyOrganizationIdentifier

@pytest.fixture
def services(session):
    o1 = Organization(id=str(uuid.uuid4()), name="test_org")
    l1 = LegacyOrganizationIdentifier(organization_id=o1.id, legacy_name="test_org")
    session.add_all([o1, l1])
    setup_base_data(session)
    audit = OrgAuditService(session)
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    validation = ValidationService(org_repo, user_repo)
    ledger_repo = LedgerRepository(session)
    ledger = LedgerService(ledger_repo)
    idempotency_repo = IdempotencyRepository(session)
    idempotency = IdempotencyService(idempotency_repo)
    wallet = WalletService(session, org_repo, user_repo, validation, ledger, idempotency)
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    
    wallet_admin = OrgWalletService(session, wallet, audit, org_repo, user_repo, pricing_service)
    gov_admin = OrgGovernanceService(session, audit)
    analytics_admin = OrgAnalyticsService(session)
    
    return wallet_admin, gov_admin, analytics_admin

# 1. Org Admin RBAC
def test_rbac_403(services, session):
    from tokenops.api.orgadmin.dependencies import verify_org_admin
    import asyncio
    
    user = session.query(User).filter_by(id=2).first()
    
    async def run_dep():
        return await verify_org_admin(active_organization="test_org", current_user=user, db=session)
    
    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_dep())
    assert exc.value.status_code == 403
    assert exc.value.detail == "INSUFFICIENT_PRIVILEGES"

def test_rbac_success(services, session):
    from tokenops.api.orgadmin.dependencies import verify_org_admin
    import asyncio
    
    user = session.query(User).filter_by(id=1).first()
    
    async def run_dep():
        return await verify_org_admin(active_organization="test_org", current_user=user, db=session)
    
    res = asyncio.run(run_dep())
    assert res.id == 1
    assert res.active_organization == "test_org"

# 2. Allocate Tokens
def test_allocate_tokens(services, session):
    wallet_admin, _, _ = services
    
    wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-1", user_id=2, token_amount=500)
    
    uw2 = session.query(UserTokenWallet).filter_by(user_id=2).first()
    assert uw2.allocated_tokens == 500
    assert uw2.remaining_tokens == 500
    
    org = session.query(OrganizationWallet).filter_by(organization_name="test_org").first()
    assert org.reserved_tokens == 1500

# 3. Reallocate Tokens
def test_reallocate_tokens(services, session):
    wallet_admin, _, _ = services
    
    wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-1", user_id=1, token_amount=500)
    wallet_admin.reallocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-2", source_user_id=1, destination_user_id=2, token_amount=200)
    
    uw1 = session.query(UserTokenWallet).filter_by(user_id=1).first()
    assert uw1.remaining_tokens == 300
    
    uw2 = session.query(UserTokenWallet).filter_by(user_id=2).first()
    assert uw2.remaining_tokens == 200

# 4. Revoke Tokens
def test_revoke_tokens(services, session):
    wallet_admin, _, _ = services
    
    wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-1", user_id=2, token_amount=500)
    wallet_admin.revoke_tokens(admin_user_id=1, organization_name="test_org", request_id="req-2", user_id=2, token_amount=200)
    
    uw2 = session.query(UserTokenWallet).filter_by(user_id=2).first()
    assert uw2.remaining_tokens == 300
    
    org = session.query(OrganizationWallet).filter_by(organization_name="test_org").first()
    assert org.reserved_tokens == 1700

# 5. Reserve Validation
def test_reserve_validation(services, session):
    wallet_admin, _, _ = services
    
    with pytest.raises(ValueError):
        wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-1", user_id=2, token_amount=5000)

# 6. Multi-org Isolation
def test_multi_org_isolation(services, session):
    # This is primarily tested in RBAC, but we can test if wallet service allows cross-org.
    # WalletService looks up user wallet by (user_id, organization_name). 
    # If the user wallet doesn't exist for the org, it fails.
    wallet_admin, _, _ = services
    with pytest.raises(ValueError):
        wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org_2", request_id="req-1", user_id=2, token_amount=500)

# 7. User Block & Unblock via UserTokenWallet
def test_user_block_unblock(services, session):
    _, gov_admin, _ = services
    
    gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=2, is_blocked=True)
    uw = session.query(UserTokenWallet).filter_by(user_id=2).first()
    assert uw.is_blocked is True
    
    gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=2, is_blocked=False)
    uw = session.query(UserTokenWallet).filter_by(user_id=2).first()
    assert uw.is_blocked is False

# 8. User Admin Block Prevention
def test_admin_block_prevention(services, session):
    _, gov_admin, _ = services
    
    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=1, is_blocked=True)
    assert exc.value.status_code == 403

# 9. Analytics Overview
def test_analytics_overview(services, session):
    _, _, analytics_admin = services
    
    data = analytics_admin.get_overview(organization_name="test_org")
    assert data.total_users == 2
    assert data.active_users == 2
    assert data.reserved_tokens == 2000
    assert data.consumed_tokens == 100
    assert data.total_requests == 5

# 10. Reports
def test_reports(services, session):
    _, _, analytics_admin = services
    
    data = analytics_admin.get_top_users(organization_name="test_org")
    assert len(data) == 1
    assert data[0].user_id == 2
    assert data[0].total_tokens == 100

def test_analytics_isolation(services, session):
    _, _, analytics_admin = services
    
    # Query for an organization with no users or usage
    data = analytics_admin.get_overview(organization_name="other_org")
    assert data.total_users == 0
    assert data.active_users == 0
    assert data.reserved_tokens == 0
    assert data.consumed_tokens == 0
    assert data.total_requests == 0

    top_users = analytics_admin.get_top_users(organization_name="other_org")
    assert len(top_users) == 0

# 11. Pagination
def test_pagination(services, session):
    wallet_admin, _, _ = services
    
    data = wallet_admin.get_users(organization_name="test_org", page=1, size=1)
    assert data.total == 2
    assert len(data.items) == 1

# 12. Idempotency
def test_idempotency(services, session):
    wallet_admin, _, _ = services
    
    wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-idem", user_id=2, token_amount=500)
    wallet_admin.allocate_tokens(admin_user_id=1, organization_name="test_org", request_id="req-idem", user_id=2, token_amount=500)
    
    uw = session.query(UserTokenWallet).filter_by(user_id=2).first()
    assert uw.allocated_tokens == 500  # Only processed once!

# 13. P0-3 Regression: get_reserve() returns ReserveWalletView without wallet.consumed_tokens AttributeError
def test_get_reserve_consumed_tokens(services, session):
    wallet_admin, _, _ = services
    reserve = wallet_admin.get_reserve("test_org")
    assert reserve is not None
    assert reserve.organization_name == "test_org"
    assert reserve.purchased_tokens == 2000
    assert reserve.reserved_tokens == 2000
    assert reserve.allocated_tokens == 0
    assert reserve.consumed_tokens == 100  # Fallback to OrganizationUsageSummary.total_tokens
    assert reserve.remaining_tokens == 2000

# 14. P0-1 Regression: Quota request submit and query using TenantResolverService.resolve()
def test_quota_request_creation_and_resolution(services, session):
    from tokenops.services.tenant_resolver_service import TenantResolverService
    from tokenops.models.quota_request import TokenQuotaRequest, QuotaRequestType, QuotaRequestStatus
    
    resolver = TenantResolverService(session)
    org_id, org = resolver.resolve("test_org")
    assert org_id is not None
    assert org.name == "test_org"
    
    # Create quota request
    quota_req = TokenQuotaRequest(
        organization_name=org.name,
        organization_id=org_id,
        request_type=QuotaRequestType.TOKEN_INCREASE,
        requested_tokens=5000,
        requested_by=1,
        status=QuotaRequestStatus.REQUESTED,
        remarks="Need more tokens for Q3",
    )
    session.add(quota_req)
    session.commit()
    session.refresh(quota_req)
    
    assert quota_req.id is not None
    assert quota_req.organization_id == org_id
    assert quota_req.requested_tokens == 5000
    
    # Query back as done in get_my_org_quota_requests
    found = session.query(TokenQuotaRequest).filter(
        (TokenQuotaRequest.organization_id == org_id) | (TokenQuotaRequest.organization_name == org.name)
    ).all()
    assert len(found) == 1
    assert found[0].requested_tokens == 5000


# ── F6 Regression Tests: Organization-Scoped Admin Block Guards & Multi-Tenant Isolation ──

def test_f6_self_block_prevention(services, session):
    _, gov_admin, _ = services
    # Admin User 1 tries to block themselves
    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=1, is_blocked=True)
    assert exc.value.status_code == 403
    assert "Cannot block" in exc.value.detail

def test_f6_admin_role_prevention(services, session):
    _, gov_admin, _ = services
    # Setup user 30 with OrganizationRole name="Admin"
    role_admin = OrganizationRole(id=10, organization_name="test_org", name="Admin")
    u30 = User(id=30, email="admin_role@test.com")
    rm30 = UserOrganizationRole(user_id=30, organization_name="test_org", role_id=10)
    uw30 = UserTokenWallet(user_id=30, organization_name="test_org", allocated_tokens=100, remaining_tokens=100)
    session.add_all([role_admin, u30, rm30, uw30])
    session.commit()

    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=30, is_blocked=True)
    assert exc.value.status_code == 403
    assert "Cannot block another Organization Admin" in exc.value.detail

def test_f6_org_admin_role_prevention(services, session):
    _, gov_admin, _ = services
    # Setup user 31 with existing OrganizationRole name="ORG_ADMIN" (role_id=1)
    u31 = User(id=31, email="org_admin_role@test.com")
    rm31 = UserOrganizationRole(user_id=31, organization_name="test_org", role_id=1)
    uw31 = UserTokenWallet(user_id=31, organization_name="test_org", allocated_tokens=100, remaining_tokens=100)
    session.add_all([u31, rm31, uw31])
    session.commit()

    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=31, is_blocked=True)
    assert exc.value.status_code == 403
    assert "Cannot block another Organization Admin" in exc.value.detail

def test_f6_legacy_admin_prevention(services, session):
    _, gov_admin, _ = services
    # Setup legacy user 32 with is_org_admin=True and matching native org, NO role mapping
    u32 = User(id=32, email="legacy_admin@test.com", organization_name="test_org", is_org_admin=True)
    uw32 = UserTokenWallet(user_id=32, organization_name="test_org", allocated_tokens=100, remaining_tokens=100)
    session.add_all([u32, uw32])
    session.commit()

    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=1, organization_name="test_org", user_id=32, is_blocked=True)
    assert exc.value.status_code == 403
    assert "Cannot block another Organization Admin" in exc.value.detail

def test_f6_multi_org_admin_in_x_member_in_y(services, session):
    _, gov_admin, _ = services
    # User 50 has native User.is_org_admin=True, User.organization_name="OrgX", and is ORG_ADMIN in Org X, but MEMBER in Org Y
    role_admin_x = OrganizationRole(id=20, organization_name="OrgX", name="ORG_ADMIN")
    role_member_y = OrganizationRole(id=21, organization_name="OrgY", name="MEMBER")
    u50 = User(id=50, email="user50@test.com", organization_name="OrgX", is_org_admin=True)
    rm_x = UserOrganizationRole(user_id=50, organization_name="OrgX", role_id=20)
    rm_y = UserOrganizationRole(user_id=50, organization_name="OrgY", role_id=21)
    uw_x = UserTokenWallet(user_id=50, organization_name="OrgX", allocated_tokens=500, remaining_tokens=500, is_blocked=False)
    uw_y = UserTokenWallet(user_id=50, organization_name="OrgY", allocated_tokens=500, remaining_tokens=500, is_blocked=False)
    
    session.add_all([role_admin_x, role_member_y, u50, rm_x, rm_y, uw_x, uw_y])
    session.commit()

    # 1. In Org X: Attempt to block User 50 -> Fails with 403 (User is Admin in Org X)
    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=1, organization_name="OrgX", user_id=50, is_blocked=True)
    assert exc.value.status_code == 403

    # 2. In Org Y: Attempt to block User 50 -> Succeeds (User is only Member in Org Y)
    gov_admin.set_user_block_status(admin_user_id=2, organization_name="OrgY", user_id=50, is_blocked=True)
    
    # 3. Verify Org Y wallet is blocked, while Org X wallet remains unblocked
    session.refresh(uw_y)
    session.refresh(uw_x)
    assert uw_y.is_blocked is True
    assert uw_x.is_blocked is False

def test_f6_multi_org_member_in_x_admin_in_y(services, session):
    _, gov_admin, _ = services
    # User 51 is MEMBER in Org X, but Admin in Org Y
    role_member_x = OrganizationRole(id=22, organization_name="OrgX", name="MEMBER")
    role_admin_y = OrganizationRole(id=23, organization_name="OrgY", name="Admin")
    u51 = User(id=51, email="user51@test.com")
    rm_x = UserOrganizationRole(user_id=51, organization_name="OrgX", role_id=22)
    rm_y = UserOrganizationRole(user_id=51, organization_name="OrgY", role_id=23)
    uw_x = UserTokenWallet(user_id=51, organization_name="OrgX", allocated_tokens=500, remaining_tokens=500, is_blocked=False)
    uw_y = UserTokenWallet(user_id=51, organization_name="OrgY", allocated_tokens=500, remaining_tokens=500, is_blocked=False)
    
    session.add_all([role_member_x, role_admin_y, u51, rm_x, rm_y, uw_x, uw_y])
    session.commit()

    # 1. In Org X: Attempt to block User 51 -> Succeeds (User is Member in Org X)
    gov_admin.set_user_block_status(admin_user_id=1, organization_name="OrgX", user_id=51, is_blocked=True)
    session.refresh(uw_x)
    assert uw_x.is_blocked is True

    # 2. In Org Y: Attempt to block User 51 -> Fails with 403 (User is Admin in Org Y)
    with pytest.raises(HTTPException) as exc:
        gov_admin.set_user_block_status(admin_user_id=2, organization_name="OrgY", user_id=51, is_blocked=True)
    assert exc.value.status_code == 403

    # Org Y wallet remains unblocked
    session.refresh(uw_y)
    assert uw_y.is_blocked is False

def test_f6_block_in_x_does_not_affect_y_wallet(services, session):
    _, gov_admin, _ = services
    # User 52 is regular member in both Org X and Org Y
    role_member_x = OrganizationRole(id=24, organization_name="OrgX", name="MEMBER")
    role_member_y = OrganizationRole(id=25, organization_name="OrgY", name="MEMBER")
    u52 = User(id=52, email="user52@test.com")
    rm_x = UserOrganizationRole(user_id=52, organization_name="OrgX", role_id=24)
    rm_y = UserOrganizationRole(user_id=52, organization_name="OrgY", role_id=25)
    uw_x = UserTokenWallet(user_id=52, organization_name="OrgX", allocated_tokens=500, remaining_tokens=500, is_blocked=False)
    uw_y = UserTokenWallet(user_id=52, organization_name="OrgY", allocated_tokens=500, remaining_tokens=500, is_blocked=False)
    
    session.add_all([role_member_x, role_member_y, u52, rm_x, rm_y, uw_x, uw_y])
    session.commit()

    # Block User 52 in Org X
    gov_admin.set_user_block_status(admin_user_id=1, organization_name="OrgX", user_id=52, is_blocked=True)

    session.refresh(uw_x)
    session.refresh(uw_y)
    assert uw_x.is_blocked is True
    assert uw_y.is_blocked is False


