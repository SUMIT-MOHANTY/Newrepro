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
        org_id = None
        org_name = tx.organization_name
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(self.repo.session)
            org_id, org = resolver.resolve(tx.organization_name)
            org_name = org.name
        except Exception:
            pass

        project_tok = tx.project_token
        project_nm = tx.project_name
        # Guarantee that AI debit transactions are never recorded without a concrete project token
        if tx.transaction_type in ("AI_CONSUMPTION", "PAYG_USAGE"):
            if not project_tok or (org_name and project_tok.strip().lower() == org_name.strip().lower()):
                try:
                    from tokenops.services.project_token_resolver import resolve_or_ensure_project_token
                    project_tok, project_nm = resolve_or_ensure_project_token(
                        session=self.repo.session,
                        user_id=tx.user_id,
                        organization_name=org_name,
                        candidate_project_token=tx.project_token,
                        candidate_project_name=tx.project_name
                    )
                except Exception:
                    pass

        entry = TokenTransactionLedger(
            organization_name=org_name,
            organization_id=org_id,
            user_id=tx.user_id,
            transaction_type=tx.transaction_type,
            token_delta=tx.token_delta,
            balance_after=balance_after,
            reference_id=tx.reference_id,
            purpose=tx.purpose,
            project_token=project_tok,
            project_name=project_nm,
            remarks=tx.remarks
        )
        self.repo.append(entry)

    def get_audit_history(self, organization_name: str, limit: int = 100) -> list[TokenTransactionLedger]:
        return self.repo.get_history(organization_name, limit)
