import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from database import Base
from tokenops.services.wallet_service import WalletService
from tokenops.services.validation_service import ValidationService
from tokenops.services.ledger_service import LedgerService
from tokenops.services.idempotency_service import IdempotencyService
from tokenops.repositories.organization_wallet import OrganizationWalletRepository
from tokenops.repositories.user_wallet import UserWalletRepository
from tokenops.repositories.ledger import LedgerRepository
from tokenops.repositories.idempotency import IdempotencyRepository
from tokenops.models import OrganizationWallet, UserTokenWallet
from models import User
from tokenops.utils.retry import retry_on_lock
from sqlite3 import OperationalError
from sqlalchemy.exc import OperationalError as SAOperationalError

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def wallet_service(session: Session):
    org_repo = OrganizationWalletRepository(session)
    user_repo = UserWalletRepository(session)
    val_service = ValidationService(org_repo, user_repo)
    ledger = LedgerService(LedgerRepository(session))
    idempotency = IdempotencyService(IdempotencyRepository(session))
    return WalletService(session, org_repo, user_repo, val_service, ledger, idempotency)

def test_negative_amounts(wallet_service: WalletService):
    with pytest.raises(ValueError, match="Amount must be positive"):
        wallet_service.purchase_tokens("Org", -100)
    with pytest.raises(ValueError, match="Amount must be positive"):
        wallet_service.allocate_tokens(1, "Org", 0)
    with pytest.raises(ValueError, match="Amount must be positive"):
        wallet_service.reallocate_tokens(1, 2, "Org", -1)
    with pytest.raises(ValueError, match="Amount must be positive"):
        wallet_service.revoke_tokens(1, "Org", 0)

def test_missing_wallets(wallet_service: WalletService):
    req = str(uuid.uuid4())
    with pytest.raises(ValueError, match="Insufficient available tokens"):
        wallet_service.allocate_tokens(1, "NonExistentOrg", 100, req)

def test_retry_decorator():
    attempts = 0
    
    @retry_on_lock(max_retries=3)
    def locked_function():
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise SAOperationalError("database is locked", None, None)
        return "success"
        
    assert locked_function() == "success"
    assert attempts == 4
    
    attempts = 0
    @retry_on_lock(max_retries=2)
    def fail_function():
        nonlocal attempts
        attempts += 1
        raise SAOperationalError("database is locked", None, None)
        
    with pytest.raises(SAOperationalError):
        fail_function()
    assert attempts == 3

from tokenops.services.pricing_service import PricingService
def test_pricing_invalidation():
    PricingService._pricing_cache["gpt-4"] = (0.03, 9999999999)
    PricingService._pricing_cache["gpt-3.5"] = (0.002, 9999999999)
    
    PricingService.invalidate("gpt-4")
    assert "gpt-4" not in PricingService._pricing_cache
    assert "gpt-3.5" in PricingService._pricing_cache
    
    PricingService.invalidate_all()
    assert len(PricingService._pricing_cache) == 0

from tokenops.repositories.usage_summary import UsageSummaryRepository
from tokenops.repositories.pricing import PricingRepository
from tokenops.models import OrganizationUsageSummary, ModelPricing
def test_other_repos(session: Session):
    usage_repo = UsageSummaryRepository(session)
    usage = OrganizationUsageSummary(organization_name="Org", request_count=10, total_tokens=100, total_cost=0.0)
    session.add(usage)
    session.commit()
    
    pricing_repo = PricingRepository(session)
    pricing = ModelPricing(model_name="gpt-4", price_per_token=0.03)
    session.add(pricing)
    session.commit()
    
    res2 = pricing_repo.get_active_price("gpt-4")
    assert res2 is not None

def test_validation_integrity_error(session: Session, wallet_service: WalletService):
    wallet_service.org_repo.update_balance("Org", 100, 100) # Creates dummy if we need to? No, wallet needs to be created.
    # Create wallet with invalid reserve
    wallet = OrganizationWallet(organization_name="Org", purchased_tokens=100, remaining_tokens=100, reserved_tokens=0)
    session.add(wallet)
    session.commit()
    
    with pytest.raises(ValueError, match="Organization reserve integrity error"):
        wallet_service.validation.validate_sufficient_org_reserve("Org", 10)
        
    uwallet = UserTokenWallet(user_id=1, organization_name="Org", allocated_tokens=100, consumed_tokens=0, remaining_tokens=50)
    session.add(uwallet)
    session.commit()
    with pytest.raises(ValueError, match="User remaining integrity error"):
        wallet_service.validation.validate_sufficient_user_balance(1, "Org", 10)
