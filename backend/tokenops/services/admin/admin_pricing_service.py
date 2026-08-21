from sqlalchemy.orm import Session
from tokenops.services.pricing_service import PricingService
from tokenops.services.admin.admin_audit_service import AdminAuditService
from tokenops.repositories.pricing import PricingRepository
from tokenops.models.pricing import ModelPricing
from decimal import Decimal
from typing import List
from tokenops.schemas.superadmin import PricingView

class AdminPricingService:
    def __init__(
        self,
        session: Session,
        audit_service: AdminAuditService,
        pricing_repo: PricingRepository
    ):
        self.session = session
        self.audit_service = audit_service
        self.pricing_repo = pricing_repo

    def get_all_pricing(self) -> List[PricingView]:
        models = self.session.query(ModelPricing).all()
        return [
            PricingView(
                model_name=m.model_name,
                price_per_token=float(m.price_per_token),
                is_active=m.is_active
            ) for m in models
        ]

    def add_model(self, admin_user_id: int, model_name: str, price_per_token: float):
        with self.session.begin():
            m = self.session.query(ModelPricing).filter_by(model_name=model_name).first()
            if m:
                # If exists, we don't recreate, we just ensure it exists.
                return m
            
            m = ModelPricing(
                model_name=model_name,
                price_per_token=Decimal(str(price_per_token)),
                is_active=False # Default inactive as per requirements
            )
            self.session.add(m)
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="ADD_MODEL",
                target_entity=model_name,
                details={"price_per_token": price_per_token}
            )

    def update_price(self, admin_user_id: int, model_name: str, price_per_token: float):
        with self.session.begin():
            m = self.session.query(ModelPricing).filter_by(model_name=model_name).first()
            if not m:
                # Add if not exists but we activate it?
                # The requirement says PUT /{model_name} -> Update pricing. 
                # Let's assume it exists, or create it if it doesn't.
                m = ModelPricing(model_name=model_name, is_active=True)
                self.session.add(m)
                
            m.price_per_token = Decimal(str(price_per_token))
            m.is_active = True
            
            self.audit_service.log_action(
                admin_user_id=admin_user_id,
                action="UPDATE_PRICE",
                target_entity=model_name,
                details={"price_per_token": price_per_token}
            )
            
            # Invalidate the cache
            PricingService.invalidate(model_name)
