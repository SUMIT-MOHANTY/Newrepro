"""
TokenOps — PAYG Billing & Detailed Invoice Generation Tests (Option C).

Verifies:
1. PAYG Request & Approval Flow
2. PAYG Usage Separation (Prepaid reserves & wallets untouched)
3. Configurable Soft Limit (warning without blocking)
4. Configurable Hard Limit (blocks consumption when reached with 402)
5. Limit Increase Request & Super Admin Approval
6. Detailed Billing-Period Invoice Generation (auditable tokens & costs)
7. Historical Pricing Snapshot Preservation
8. Duplicate Invoice Prevention (Unique month/org constraint)
9. Batch Monthly & Manual On-Demand Generation
10. Billing Email Delivery & Routing
"""

import json
import uuid
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import User, AIUsageLog, UserOrganizationRole, OrganizationRole
from tokenops.models.organization import Organization, LegacyOrganizationIdentifier
from tokenops.models.token_wallet import OrganizationWallet, UserOrganization, UserTokenWallet
from tokenops.models.pricing import ModelPricing
from tokenops.models.payg import PAYGRequest, PAYGStatus, PAYGInvoice, InvoiceStatus
from tokenops.models.quota_request import TokenQuotaRequest, QuotaRequestType, QuotaRequestStatus
from tokenops.models.ledger import TokenTransactionLedger, TransactionType
from tokenops.models.summary import OrganizationUsageSummary, UserUsageSummary
from tokenops.models.idempotency import IdempotencyKey

from tokenops.services.pricing_service import PricingService
from tokenops.services.wallet_service import WalletService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.usage_summary_service import UsageSummaryService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.services.validation_service import ValidationService
from tokenops.services.tenant_resolver_service import TenantResolverService
from tokenops.services.tokenops_orchestrator import TokenOpsOrchestrator
from tokenops.services.payg_invoice_service import PAYGInvoiceService
from tokenops.services.admin.admin_governance_service import AdminGovernanceService
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.repositories.pricing import PricingRepository
from tokenops.repositories.ledger import LedgerRepository
from tokenops.repositories.idempotency import IdempotencyRepository
from tokenops.repositories.usage_summary import UsageSummaryRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def env(session):
    # Setup Tenant Master
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="Acme Corp", is_active=True)
    alias = LegacyOrganizationIdentifier(organization_id=org_id, legacy_name="Acme Corp", is_active=True)
    
    # Org Wallet
    wallet = OrganizationWallet(
        id=org_id,
        organization_name="Acme Corp",
        organization_id=org_id,
        purchased_tokens=10000,
        remaining_tokens=10000,
        reserved_tokens=10000,
        payg_enabled=False,
        payg_current_spend_usd=Decimal("0.0"),
        payg_billing_email="billing@acmecorp.com"
    )
    
    # Users
    admin_user = User(id=1, email="admin@acmecorp.com", organization_name="Acme Corp", is_org_admin=True)
    member_user = User(id=2, email="developer@acmecorp.com", organization_name="Acme Corp")
    super_admin = User(id=99, email="superadmin@dsuite.com", is_super_admin=True)
    
    # Memberships
    m1 = UserOrganization(user_id=1, organization_name="Acme Corp", organization_id=org_id, is_active=True)
    m2 = UserOrganization(user_id=2, organization_name="Acme Corp", organization_id=org_id, is_active=True)
    
    # User Wallet (Prepaid)
    u_wallet = UserTokenWallet(
        user_id=2,
        organization_name="Acme Corp",
        organization_id=org_id,
        allocated_tokens=2000,
        remaining_tokens=2000,
        consumed_tokens=0,
        is_blocked=False
    )
    
    # Pricing: $0.00003 per token
    pricing_gpt4 = ModelPricing(model_name="gpt-4o", price_per_token=Decimal("0.00003000"), is_active=True)
    pricing_claude = ModelPricing(model_name="claude-3-5-sonnet", price_per_token=Decimal("0.00005000"), is_active=True)
    
    session.add_all([org, alias, wallet, admin_user, member_user, super_admin, m1, m2, u_wallet, pricing_gpt4, pricing_claude])
    session.commit()
    
    # Build Service Graph
    pricing_repo = PricingRepository(session)
    pricing_service = PricingService(pricing_repo)
    PricingService.invalidate_all()
    
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    validation = ValidationService(org_repo, user_repo)
    ledger_repo = LedgerRepository(session)
    ledger_service = LedgerService(ledger_repo)
    idempotency_repo = IdempotencyRepository(session)
    idempotency_service = IdempotencyService(idempotency_repo)
    usage_repo = UsageSummaryRepository(session)
    usage_service = UsageSummaryService(usage_repo)
    tenant_resolver = TenantResolverService(session)
    wallet_service = WalletService(session, org_repo, user_repo, validation, ledger_service, idempotency_service)
    audit_service = AdminAuditService(session)
    
    orchestrator = TokenOpsOrchestrator(
        session=session,
        validation=validation,
        pricing=pricing_service,
        wallet=wallet_service,
        ledger=ledger_service,
        usage_summary=usage_service,
        idempotency=idempotency_service,
        tenant_resolver=tenant_resolver
    )
    
    gov_service = AdminGovernanceService(
        session=session,
        audit_service=audit_service,
        org_repo=org_repo,
        user_repo=user_repo,
        wallet_service=wallet_service
    )
    
    invoice_service = PAYGInvoiceService(session=session, pricing_service=pricing_service)
    
    return {
        "session": session,
        "org_id": org_id,
        "orchestrator": orchestrator,
        "gov_service": gov_service,
        "invoice_service": invoice_service,
        "pricing_service": pricing_service
    }


# ── 1. PAYG Request & Approval Flow ──────────────────────────────────────────

def test_payg_request_and_approval_flow(env):
    session = env["session"]
    gov = env["gov_service"]
    
    # 1. Submit PAYG request from Org Admin
    req = TokenQuotaRequest(
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        request_type=QuotaRequestType.PAYG_ENABLEMENT,
        requested_tokens=0,
        requested_by=1,
        status=QuotaRequestStatus.REQUESTED,
        remarks="Need PAYG for variable AI workloads"
    )
    session.add(req)
    session.commit()
    
    # 2. Super Admin approves
    gov.handle_quota_request(admin_user_id=99, request_id=req.id, approve=True, remarks="Approved PAYG access")
    
    session.refresh(req)
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    
    assert req.status == QuotaRequestStatus.APPROVED.value
    assert wallet.payg_enabled is True


# ── 2. PAYG Usage Separation (Prepaid Wallets & Reserves Untouched) ─────────

def test_payg_usage_separation(env):
    session = env["session"]
    orch = env["orchestrator"]
    
    # Enable PAYG
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    session.commit()
    
    # Run AI inference in PAYG mode
    orch.pre_execute(user_id=2, organization_name="Acme Corp")
    orch.post_execute(
        request_id="req-payg-1",
        user_id=2,
        organization_name="Acme Corp",
        model_name="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=500
    )
    
    session.refresh(wallet)
    u_wallet = session.query(UserTokenWallet).filter_by(user_id=2).first()
    
    # Invariant: Prepaid balances & reserves are completely untouched
    assert wallet.reserved_tokens == 10000
    assert wallet.remaining_tokens == 10000
    assert u_wallet.remaining_tokens == 2000
    assert u_wallet.consumed_tokens == 1500  # Tracks user consumption in PAYG mode
    
    # Invariant: PAYG spend is tracked
    expected_cost = (1000 + 500) * 0.00003  # $0.045
    assert float(wallet.payg_current_spend_usd) == pytest.approx(expected_cost, rel=1e-5)
    
    # Invariant: Ledger records PAYG_USAGE with meaningful accumulated balance
    ledger_entry = session.query(TokenTransactionLedger).filter_by(reference_id="req-payg-1").first()
    assert ledger_entry is not None
    assert ledger_entry.transaction_type == TransactionType.PAYG_USAGE.value
    assert ledger_entry.token_delta == -1500
    assert ledger_entry.balance_after == -1500  # Cumulative PAYG token debt


# ── 3. Configurable Soft Limit (Warning Without Blocking) ───────────────────

def test_payg_soft_limit_warning_does_not_block(env, caplog):
    session = env["session"]
    orch = env["orchestrator"]
    gov = env["gov_service"]
    
    # Enable PAYG with Soft Limit = $0.05
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    session.commit()
    
    gov.set_payg_limits(admin_user_id=99, organization_name="Acme Corp", soft_limit_usd=0.05, hard_limit_usd=10.00)
    
    # Consume 3,000 tokens ($0.090) — exceeds soft limit $0.05
    orch.pre_execute(user_id=2, organization_name="Acme Corp")
    orch.post_execute(
        request_id="req-soft-1",
        user_id=2,
        organization_name="Acme Corp",
        model_name="gpt-4o",
        prompt_tokens=2000,
        completion_tokens=1000
    )
    
    # Next call should NOT raise 402/403 despite exceeding soft limit
    orch.pre_execute(user_id=2, organization_name="Acme Corp")


# ── 4. Configurable Hard Limit (Blocks Consumption When Reached) ───────────

def test_payg_hard_limit_blocks_consumption(env):
    session = env["session"]
    orch = env["orchestrator"]
    gov = env["gov_service"]
    
    # Enable PAYG with Hard Limit = $0.06
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    session.commit()
    
    gov.set_payg_limits(admin_user_id=99, organization_name="Acme Corp", hard_limit_usd=0.06)
    
    # 1. First call consumes 2,000 tokens ($0.060) -> hits hard limit exactly
    orch.pre_execute(user_id=2, organization_name="Acme Corp")
    orch.post_execute(
        request_id="req-hard-1",
        user_id=2,
        organization_name="Acme Corp",
        model_name="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=1000
    )
    
    # 2. Subsequent call must be blocked with 402 PAYG_HARD_LIMIT_REACHED
    with pytest.raises(HTTPException) as exc:
        orch.pre_execute(user_id=2, organization_name="Acme Corp")
    assert exc.value.status_code == 402
    assert exc.value.detail == "PAYG_HARD_LIMIT_REACHED"


# ── 5. Limit Increase Request & Super Admin Approval ─────────────────────────

def test_payg_limit_increase_flow(env):
    session = env["session"]
    orch = env["orchestrator"]
    gov = env["gov_service"]
    
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    wallet.payg_hard_limit_usd = Decimal("0.05")
    wallet.payg_current_spend_usd = Decimal("0.05")
    session.commit()
    
    # Blocked before increase
    with pytest.raises(HTTPException) as exc:
        orch.pre_execute(user_id=2, organization_name="Acme Corp")
    assert exc.value.status_code == 402
    
    # 1. Org Admin requests limit increase to $50.00
    req = TokenQuotaRequest(
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        request_type=QuotaRequestType.LIMIT_INCREASE,
        requested_limit_usd=Decimal("50.00"),
        requested_by=1,
        status=QuotaRequestStatus.REQUESTED,
        remarks="Increasing spending limit for launch week"
    )
    session.add(req)
    session.commit()
    
    # 2. Super Admin approves limit increase
    gov.handle_quota_request(admin_user_id=99, request_id=req.id, approve=True, remarks="Approved $50 limit")
    
    session.refresh(wallet)
    assert float(wallet.payg_hard_limit_usd) == 50.0
    
    # 3. User is now unblocked
    orch.pre_execute(user_id=2, organization_name="Acme Corp")


# ── 6. Detailed Billing-Period Invoice Generation ───────────────────────────

def test_detailed_invoice_generation(env):
    session = env["session"]
    inv_svc = env["invoice_service"]
    
    # Seed historical AI usage for month 2026-08
    log1 = AIUsageLog(
        user_id=2,
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        model="gpt-4o",
        prompt_tokens=10000,
        completion_tokens=5000,
        cost=15000 * 0.00003, # $0.45
        created_at=datetime(2026, 8, 10, 14, 30)
    )
    log2 = AIUsageLog(
        user_id=2,
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        model="claude-3-5-sonnet",
        prompt_tokens=4000,
        completion_tokens=6000,
        cost=10000 * 0.00005, # $0.50
        created_at=datetime(2026, 8, 20, 18, 0)
    )
    # Log in a different month (should be excluded)
    log_other = AIUsageLog(
        user_id=2,
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        model="gpt-4o",
        prompt_tokens=50000,
        completion_tokens=50000,
        cost=100000 * 0.00003,
        created_at=datetime(2026, 9, 1, 10, 0)
    )
    session.add_all([log1, log2, log_other])
    session.commit()
    
    # Generate Invoice for 2026-08
    inv = inv_svc.generate_invoice(organization_name="Acme Corp", billing_month="2026-08", send_email=False)
    
    assert inv is not None
    assert inv.organization_name == "Acme Corp"
    assert inv.billing_month == "2026-08"
    assert inv.prompt_tokens == 14000       # 10000 + 4000
    assert inv.completion_tokens == 11000   # 5000 + 6000
    assert inv.total_tokens == 25000
    assert float(inv.total_cost) == pytest.approx(0.95, rel=1e-4) # $0.45 + $0.50
    assert inv.invoice_status == InvoiceStatus.PENDING.value
    
    # Verify line items JSON breakdown
    line_items = json.loads(inv.line_items)
    assert len(line_items) == 2
    
    gpt_item = next(i for i in line_items if i["model"] == "gpt-4o")
    assert gpt_item["prompt_tokens"] == 10000
    assert gpt_item["completion_tokens"] == 5000
    assert gpt_item["total_tokens"] == 15000
    assert float(gpt_item["total_cost"]) == pytest.approx(0.45, rel=1e-4)


# ── 7. Pricing Snapshot / Historical Pricing Invariance ─────────────────────

def test_historical_pricing_snapshot_preservation(env):
    session = env["session"]
    inv_svc = env["invoice_service"]
    
    # Seed usage at original price ($0.00003)
    log = AIUsageLog(
        user_id=2,
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        model="gpt-4o",
        prompt_tokens=10000,
        completion_tokens=10000,
        cost=20000 * 0.00003, # $0.60
        created_at=datetime(2026, 8, 15, 12, 0)
    )
    session.add(log)
    session.commit()
    
    # Generate Invoice
    inv = inv_svc.generate_invoice(organization_name="Acme Corp", billing_month="2026-08", send_email=False)
    original_cost = float(inv.total_cost)
    assert original_cost == pytest.approx(0.60, rel=1e-4)
    
    # Later: Price is increased by 10x
    pricing = session.query(ModelPricing).filter_by(model_name="gpt-4o").first()
    pricing.price_per_token = Decimal("0.00030000")
    session.commit()
    PricingService.invalidate_all()
    
    # Query invoice back -> historical total_cost & line items must remain frozen!
    inv_retrieved = inv_svc.get_invoice(inv.id)
    assert float(inv_retrieved.total_cost) == pytest.approx(0.60, rel=1e-4)
    line_items = json.loads(inv_retrieved.line_items)
    assert line_items[0]["rate_per_token"] == 0.00003


# ── 8. Duplicate Invoice Prevention ─────────────────────────────────────────

def test_duplicate_invoice_prevention(env):
    inv_svc = env["invoice_service"]
    session = env["session"]
    
    # Seed usage
    log = AIUsageLog(
        user_id=2,
        organization_name="Acme Corp",
        organization_id=env["org_id"],
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=1000,
        cost=2000 * 0.00003,
        created_at=datetime(2026, 8, 15, 12, 0)
    )
    session.add(log)
    session.commit()
    
    # First generation
    inv1 = inv_svc.generate_invoice(organization_name="Acme Corp", billing_month="2026-08", send_email=False)
    
    # Second generation call for same org & month
    inv2 = inv_svc.generate_invoice(organization_name="Acme Corp", billing_month="2026-08", send_email=False)
    
    # Must return the identical invoice record without creating a second row
    assert inv1.id == inv2.id
    count = session.query(PAYGInvoice).filter_by(organization_name="Acme Corp", billing_month="2026-08").count()
    assert count == 1


# ── 9. Batch Monthly & Manual On-Demand Generation ──────────────────────────

def test_batch_monthly_generation(env):
    session = env["session"]
    inv_svc = env["invoice_service"]
    
    # Enable PAYG on Acme Corp
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    
    # Create second PAYG org "Beta Org"
    org2_id = str(uuid.uuid4())
    org2 = Organization(id=org2_id, name="Beta Org", is_active=True)
    alias2 = LegacyOrganizationIdentifier(organization_id=org2_id, legacy_name="Beta Org", is_active=True)
    wallet2 = OrganizationWallet(id=org2_id, organization_name="Beta Org", organization_id=org2_id, payg_enabled=True)
    
    session.add_all([org2, alias2, wallet2])
    session.commit()
    
    # Batch generate invoices for 2026-08
    invoices = inv_svc.generate_all_monthly_invoices(billing_month="2026-08")
    
    org_names = {i.organization_name for i in invoices}
    assert "Acme Corp" in org_names
    assert "Beta Org" in org_names
    assert len(invoices) == 2


# ── 10. Email Delivery & Billing Routing ────────────────────────────────────

def test_invoice_email_dispatch(env, monkeypatch):
    inv_svc = env["invoice_service"]
    session = env["session"]
    
    sent_emails = []
    def mock_send(msg):
        body_text = ""
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body_text = part.get_content()
        sent_emails.append({
            "to": msg["To"],
            "subject": msg["Subject"],
            "body": body_text
        })
        
    monkeypatch.setattr("email_service.ensure_email_delivery_configured", lambda: None)
    monkeypatch.setattr("email_service._send_email_message", mock_send)
    monkeypatch.setattr("email_service._from_header", lambda: "DSuite <billing@dsuite.ai>")
    
    # Generate and send invoice
    inv = inv_svc.generate_invoice(
        organization_name="Acme Corp",
        billing_month="2026-08",
        recipient_email="finance@acmecorp.com",
        send_email=True
    )
    
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "finance@acmecorp.com"
    assert "Acme Corp" in sent_emails[0]["subject"]
    assert "2026-08" in sent_emails[0]["subject"]
    assert "Total Tokens" in sent_emails[0]["body"]


# ── 11. Single-Request Hard-Limit Overshoot Protection ───────────────────────

def test_single_request_hard_limit_overshoot(env):
    """
    Verifies that a request whose estimated cost would push current_spend over the hard limit
    is rejected BEFORE execution (e.g. Current $95 + Estimate $10 > Limit $100 -> 402).
    """
    orchestrator = env["orchestrator"]
    session = env["session"]
    
    # Configure $100 hard limit, set current spend to $95
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    wallet.payg_hard_limit_usd = Decimal("100.00")
    wallet.payg_current_spend_usd = Decimal("95.00")
    wallet.payg_reserved_spend_usd = Decimal("0.00")
    session.commit()
    
    # Request costing $10 ($95 + $10 = $105 > $100)
    with pytest.raises(HTTPException) as exc_info:
        orchestrator.pre_execute(
            user_id=1,
            organization_name="Acme Corp",
            estimated_cost=10.00
        )
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "PAYG_HARD_LIMIT_REACHED"
    
    # Verify spend and reservations were NOT modified
    session.refresh(wallet)
    assert float(wallet.payg_current_spend_usd) == 95.00
    assert float(wallet.payg_reserved_spend_usd) == 0.00


# ── 12. Request Exactly Within Remaining Limit ──────────────────────────────

def test_request_exactly_within_remaining_limit(env):
    """
    Verifies that a request whose estimated cost brings total spend exactly to the hard limit
    is permitted and atomically reserved (e.g. Current $95 + Estimate $5 = Limit $100 -> Allowed).
    Subsequent requests are then rejected.
    """
    orchestrator = env["orchestrator"]
    session = env["session"]
    
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    wallet.payg_hard_limit_usd = Decimal("100.00")
    wallet.payg_current_spend_usd = Decimal("95.00")
    wallet.payg_reserved_spend_usd = Decimal("0.00")
    session.commit()
    
    # Exactly $5 estimate brings total committed spend to $100 <= $100
    res_cost = orchestrator.pre_execute(
        user_id=1,
        organization_name="Acme Corp",
        estimated_cost=5.00
    )
    assert res_cost == 5.00
    
    session.refresh(wallet)
    assert float(wallet.payg_current_spend_usd) == 95.00
    assert float(wallet.payg_reserved_spend_usd) == 5.00
    
    # A second request of even $0.01 exceeds the hard limit ($95 + $5 + $0.01 = $100.01 > $100)
    with pytest.raises(HTTPException) as exc_info:
        orchestrator.pre_execute(
            user_id=1,
            organization_name="Acme Corp",
            estimated_cost=0.01
        )
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "PAYG_HARD_LIMIT_REACHED"


# ── 13. Concurrent Requests Competing for Remaining Limit ───────────────────

def test_concurrent_requests_competing_for_remaining_limit(tmp_path):
    """
    Verifies that when multiple concurrent threads compete for remaining limit headroom:
    Hard limit = $100, Current spend = $90, Headroom = $10.
    5 threads each try to reserve $4. Exactly 2 succeed ($90 + $4 + $4 = $98), 3 fail with 402.
    No overshoot occurs under race conditions.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    
    db_file = str(tmp_path / "test_concurrency.db")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"timeout": 30, "check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine)
    
    # Setup initial test org and wallet
    setup_db = SessionFactory()
    org = Organization(id="org-concurrent", name="Concurrent Org", is_active=True)
    setup_db.add(org)
    user = User(id=10, email="c@org.com", organization_name="Concurrent Org", is_active=True)
    setup_db.add(user)
    uo = UserOrganization(user_id=10, organization_id="org-concurrent", organization_name="Concurrent Org", is_active=True)
    setup_db.add(uo)
    wallet = OrganizationWallet(
        id="org-concurrent",
        organization_id="org-concurrent",
        organization_name="Concurrent Org",
        payg_enabled=True,
        payg_hard_limit_usd=Decimal("100.00"),
        payg_current_spend_usd=Decimal("90.00"),
        payg_reserved_spend_usd=Decimal("0.00")
    )
    setup_db.add(wallet)
    setup_db.commit()
    setup_db.close()
    
    success_count = 0
    failure_count = 0
    lock = threading.Lock()
    
    def run_pre_execute():
        nonlocal success_count, failure_count
        db = SessionFactory()
        try:
            orch = TokenOpsOrchestrator.create(db)
            orch.pre_execute(
                user_id=10,
                organization_name="Concurrent Org",
                estimated_cost=4.00
            )
            with lock:
                success_count += 1
        except HTTPException as e:
            if e.status_code == 402:
                with lock:
                    failure_count += 1
        finally:
            db.close()
            
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_pre_execute) for _ in range(5)]
        for f in futures:
            f.result()
            
    assert success_count == 2
    assert failure_count == 3
    
    verify_db = SessionFactory()
    final_wallet = verify_db.query(OrganizationWallet).filter_by(organization_name="Concurrent Org").first()
    assert float(final_wallet.payg_current_spend_usd) == 90.00
    assert float(final_wallet.payg_reserved_spend_usd) == 8.00
    assert float(final_wallet.payg_current_spend_usd) + float(final_wallet.payg_reserved_spend_usd) <= 100.00
    verify_db.close()


# ── 14. Reservation Release on Failed Execution ──────────────────────────────

def test_reservation_release_on_failed_execution(env):
    """
    Verifies that when an execution fails or encounters an exception after pre_execute,
    calling release_reservation() cleanly restores the reserved spend without increasing actual spend.
    """
    orchestrator = env["orchestrator"]
    session = env["session"]
    
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    wallet.payg_hard_limit_usd = Decimal("100.00")
    wallet.payg_current_spend_usd = Decimal("90.00")
    wallet.payg_reserved_spend_usd = Decimal("0.00")
    session.commit()
    
    # 1. Reserve $8 in-flight
    reserved_cost = orchestrator.pre_execute(
        user_id=1,
        organization_name="Acme Corp",
        estimated_cost=8.00
    )
    assert reserved_cost == 8.00
    
    session.refresh(wallet)
    assert float(wallet.payg_reserved_spend_usd) == 8.00
    
    # 2. Simulate failure & release reservation
    orchestrator.release_reservation(
        organization_name="Acme Corp",
        reserved_cost=reserved_cost
    )
    
    session.refresh(wallet)
    assert float(wallet.payg_reserved_spend_usd) == 0.00
    assert float(wallet.payg_current_spend_usd) == 90.00
    
    # 3. Verify headroom restored: another $8 request can now succeed
    res_cost2 = orchestrator.pre_execute(
        user_id=1,
        organization_name="Acme Corp",
        estimated_cost=8.00
    )
    assert res_cost2 == 8.00


# ── 15. Actual-Cost Settlement After Successful Execution ───────────────────

def test_actual_cost_settlement_after_successful_execution(env):
    """
    Verifies that on successful execution, post_execute releases the in-flight reservation
    and settles using the actual LLM cost (e.g. Reserved $8, Actual $6.50 -> Reserved $0, Current $96.50).
    """
    orchestrator = env["orchestrator"]
    session = env["session"]
    
    wallet = session.query(OrganizationWallet).filter_by(organization_name="Acme Corp").first()
    wallet.payg_enabled = True
    wallet.payg_hard_limit_usd = Decimal("100.00")
    wallet.payg_current_spend_usd = Decimal("90.00")
    wallet.payg_reserved_spend_usd = Decimal("0.00")
    session.commit()
    
    # 1. Reserve $8 in-flight
    reserved_cost = orchestrator.pre_execute(
        user_id=1,
        organization_name="Acme Corp",
        estimated_cost=8.00
    )
    assert reserved_cost == 8.00
    
    # 2. Complete execution with actual cost (e.g. 100,000 tokens @ $0.00003/token = $3.00)
    orchestrator.post_execute(
        user_id=1,
        organization_name="Acme Corp",
        model_name="gpt-4o",
        prompt_tokens=50000,
        completion_tokens=50000,
        request_id=str(uuid.uuid4()),
        reserved_cost=reserved_cost
    )
    
    session.refresh(wallet)
    assert float(wallet.payg_reserved_spend_usd) == 0.00
    assert float(wallet.payg_current_spend_usd) == 93.00
