from tokenops.repositories.ledger import LedgerRepository
from tokenops.models.ledger import TokenTransactionLedger
from tokenops.domain import TokenTransaction

class LedgerService:
    def __init__(self, repo: LedgerRepository):
        self.repo = repo

    def write_entry(self, tx: TokenTransaction, balance_after: int) -> None:
        """
        Creates an immutable ledger entry.
        Note: The actual DB insertion happens when the parent transaction commits.
        """
        entry = TokenTransactionLedger(
            organization_name=tx.organization_name,
            user_id=tx.user_id,
            transaction_type=tx.transaction_type,
            token_delta=tx.token_delta,
            balance_after=balance_after,
            reference_id=tx.reference_id,
            remarks=tx.remarks
        )
        self.repo.append(entry)

    def get_audit_history(self, organization_name: str, limit: int = 100) -> list[TokenTransactionLedger]:
        return self.repo.get_history(organization_name, limit)
