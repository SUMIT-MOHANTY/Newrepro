from sqlalchemy.orm import Session
from tokenops.models import ModelPricing
from decimal import Decimal

class PricingRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_active_price(self, model_name: str) -> Decimal | None:
        record = self.session.query(ModelPricing).filter(
            ModelPricing.model_name == model_name,
            ModelPricing.is_active == True
        ).order_by(ModelPricing.effective_from.desc()).first()
        
        return record.price_per_token if record else None
