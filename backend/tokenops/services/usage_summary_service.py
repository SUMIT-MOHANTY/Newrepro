from tokenops.repositories.usage_summary import UsageSummaryRepository

class UsageSummaryService:
    def __init__(self, repo: UsageSummaryRepository):
        self.repo = repo

    def increment_rollup(self, organization_name: str, prompt_tokens: int, completion_tokens: int, total_cost: float) -> None:
        """
        Updates the dashboard rollup table.
        Does not scan the AIUsageLog table, performs an atomic O(1) increment.
        """
        self.repo.increment_usage(
            organization_name=organization_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost=total_cost
        )
