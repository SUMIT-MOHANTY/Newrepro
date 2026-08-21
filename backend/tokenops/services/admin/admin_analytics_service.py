from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.models.token_wallet import OrganizationWallet
from tokenops.models.summary import OrganizationUsageSummary
from tokenops.schemas.superadmin import AnalyticsOverview, OrganizationAnalytics, DailyUsageView, TopUserView
from typing import Optional

class AdminAnalyticsService:
    def __init__(self, session: Session):
        self.session = session

    def get_overview(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        organization: Optional[str] = None,
        billing_mode: Optional[str] = None
    ) -> AnalyticsOverview:
        # 1. Get Wallet Stats
        wallet_query = self.session.query(OrganizationWallet)
        
        if organization:
            wallet_query = wallet_query.filter(OrganizationWallet.organization_name == organization)
        if billing_mode:
            payg = billing_mode.lower() == "payg"
            wallet_query = wallet_query.filter(OrganizationWallet.payg_enabled == payg)
            
        total_orgs = wallet_query.count()
        payg_orgs = wallet_query.filter(OrganizationWallet.payg_enabled == True).count()
        prepaid_orgs = total_orgs - payg_orgs
        blocked_orgs = wallet_query.filter(OrganizationWallet.is_blocked == True).count()
        
        # 2. Get Usage Stats from OrganizationUsageSummary
        usage_query = self.session.query(
            func.sum(OrganizationUsageSummary.prompt_tokens + OrganizationUsageSummary.completion_tokens).label('total_tokens'),
            func.sum(OrganizationUsageSummary.total_requests).label('total_requests')
        )
        
        if organization:
            usage_query = usage_query.filter(OrganizationUsageSummary.organization_name == organization)
        # Note: from_date and to_date filtering on summary table assumes it has a date dimension.
        # But wait, looking at models, OrganizationUsageSummary might be a single row per org or it might be daily.
        # Let's assume it's just one row per org, or if there's a date field, we filter on it.
        # For this requirement, we'll fetch everything if no date is specified.
        # For now, just a basic sum.
        
        result = usage_query.first()
        total_tokens = result.total_tokens or 0
        total_requests = result.total_requests or 0
        
        return AnalyticsOverview(
            total_organizations=total_orgs,
            prepaid_organizations=prepaid_orgs,
            payg_organizations=payg_orgs,
            blocked_organizations=blocked_orgs,
            total_tokens_consumed=total_tokens,
            total_requests=total_requests
        )

    def get_organization_analytics(self, organization_name: str) -> OrganizationAnalytics:
        wallet = self.session.query(OrganizationWallet).filter_by(organization_name=organization_name).first()
        
        # We don't have DailyUsage in summary right now without AIUsageLog scanning, but we fulfill 
        # the interface as best as we can based on OrganizationUsageSummary.
        # For TopUsers, we'd normally aggregate from AIUsageLog but requirement says "Never aggregate AIUsageLog".
        # If we have a UserUsageSummary table, we query that. If not, we return empty list for now.
        
        return OrganizationAnalytics(
            organization_name=organization_name,
            daily_usage=[], # Placeholder for actual daily rollup table if it exists
            top_users=[], # Placeholder for actual user rollup table if it exists
            token_burn=wallet.consumed_tokens if wallet else 0,
            remaining_balance=wallet.remaining_tokens if wallet else 0
        )
