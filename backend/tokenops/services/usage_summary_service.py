from tokenops.repositories.usage_summary import UsageSummaryRepository

class UsageSummaryService:
    def __init__(self, repo: UsageSummaryRepository):
        self.repo = repo

    def increment_rollup(self, organization_name: str, prompt_tokens: int, completion_tokens: int, total_cost: float) -> None:
        """
        Updates the org-level dashboard rollup table.
        Performs an atomic O(1) increment.
        """
        self.repo.increment_usage(
            organization_name=organization_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost=total_cost
        )

    def increment_user_rollup(self, user_id: int, organization_name: str, prompt_tokens: int, completion_tokens: int, total_cost: float) -> None:
        """
        Updates the per-user dashboard rollup table.
        Called for both PREPAID and PAYG so that user-level analytics are preserved.
        """
        self.repo.increment_user_usage(
            user_id=user_id,
            organization_name=organization_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost=total_cost
        )

