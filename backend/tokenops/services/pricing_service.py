import time
from decimal import Decimal
from tokenops.repositories.pricing import PricingRepository
from tokenops.models.pricing import DEFAULT_PRICE_PER_TOKEN

class PricingService:
    # Class-level cache dictionary.
    # In a multi-worker environment, this is local to the worker.
    _pricing_cache: dict[str, tuple[Decimal, float]] = {}
    TTL_SECONDS = 300  # 5 minutes

    def __init__(self, repo: PricingRepository):
        self.repo = repo

    def get_price(self, model_name: str) -> Decimal:
        """
        Returns the active price for a model.
        Uses a 5-minute in-memory cache to avoid DB hits on every LLM call.
        """
        now = time.time()
        
        # Check cache
        if model_name in self._pricing_cache:
            price, timestamp = self._pricing_cache[model_name]
            if now - timestamp < self.TTL_SECONDS:
                return price

        # Cache miss or expired, fetch from DB
        price = self.repo.get_active_price(model_name)
        
        # Fallback to default if not found
        if price is None:
            price = DEFAULT_PRICE_PER_TOKEN
            
        # Update cache
        self._pricing_cache[model_name] = (price, now)
        return price

    @classmethod
    def invalidate(cls, model_name: str) -> None:
        """Invalidate the cache for a specific model."""
        if model_name in cls._pricing_cache:
            del cls._pricing_cache[model_name]

    @classmethod
    def invalidate_all(cls) -> None:
        """Invalidate the entire pricing cache."""
        cls._pricing_cache.clear()
