from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert
from tokenops.models import OrganizationUsageSummary
from datetime import datetime

class UsageSummaryRepository:
    def __init__(self, session: Session):
        self.session = session

    def increment_usage(self, organization_name: str, prompt_tokens: int, completion_tokens: int, total_cost: float) -> None:
        """
        Atomically increments usage summary or inserts a new row if it doesn't exist.
        """
        total_tokens = prompt_tokens + completion_tokens
        
        stmt = insert(OrganizationUsageSummary).values(
            organization_name=organization_name,
            total_prompt_tokens=prompt_tokens,
            total_completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            total_cost=total_cost,
            request_count=1,
            last_updated=datetime.utcnow()
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=['organization_name'],
            set_={
                'total_prompt_tokens': OrganizationUsageSummary.total_prompt_tokens + prompt_tokens,
                'total_completion_tokens': OrganizationUsageSummary.total_completion_tokens + completion_tokens,
                'total_tokens': OrganizationUsageSummary.total_tokens + total_tokens,
                'total_cost': OrganizationUsageSummary.total_cost + total_cost,
                'request_count': OrganizationUsageSummary.request_count + 1,
                'last_updated': datetime.utcnow()
            }
        )
        
        self.session.execute(stmt)
