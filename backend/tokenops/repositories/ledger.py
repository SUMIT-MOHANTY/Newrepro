from sqlalchemy.orm import Session
from tokenops.models import TokenTransactionLedger

class LedgerRepository:
    def __init__(self, session: Session):
        self.session = session

    def append(self, entry: TokenTransactionLedger) -> None:
        """
        Appends an immutable entry to the ledger.
        """
        self.session.add(entry)

    def get_history(self, organization_name: str, limit: int = 100) -> list[TokenTransactionLedger]:
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.session)
            org_id, org = resolver.resolve(organization_name)
            history = self.session.query(TokenTransactionLedger).filter(
                TokenTransactionLedger.organization_id == org_id
            ).order_by(TokenTransactionLedger.created_at.desc()).limit(limit).all()
            if history:
                for row in history:
                    if not row.organization_id:
                        row.organization_id = org_id
                return history
        except Exception:
            pass

        return self.session.query(TokenTransactionLedger).filter(
            TokenTransactionLedger.organization_name == organization_name
        ).order_by(TokenTransactionLedger.created_at.desc()).limit(limit).all()
