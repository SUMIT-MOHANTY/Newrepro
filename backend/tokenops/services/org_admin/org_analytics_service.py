from sqlalchemy.orm import Session
from sqlalchemy import func
from tokenops.models.token_wallet import OrganizationWallet, UserOrganization
from tokenops.models.summary import OrganizationUsageSummary, UserUsageSummary
from tokenops.models.ledger import TokenTransactionLedger
from tokenops.schemas.orgadmin import (
    OrgKPIView, TopUserView, FinancialLedgerView, PaginatedLedgerResponse,
    UserConsumptionView, DailyUsageView, UsageReportView
)
from typing import Optional, List

class OrgAnalyticsService:
    def __init__(self, session: Session):
        self.session = session

    def get_overview(self, organization_name: str) -> OrgKPIView:
        # Users
        total_users = self.session.query(UserOrganization).filter_by(organization_name=organization_name).count()
        active_users = self.session.query(UserOrganization).filter_by(organization_name=organization_name, is_active=True).count()
        
        # Reserve Wallet
        wallet = self.session.query(OrganizationWallet).filter_by(organization_name=organization_name).first()
        reserved_tokens = wallet.reserved_tokens if wallet else 0
        remaining_tokens = wallet.remaining_tokens if wallet else 0
        
        # Usage Summary
        usage = self.session.query(OrganizationUsageSummary).filter_by(organization_name=organization_name).first()
        consumed_tokens = usage.total_tokens if usage else 0
        total_requests = usage.request_count if usage else 0
        
        return OrgKPIView(
            total_users=total_users,
            active_users=active_users,
            reserved_tokens=reserved_tokens,
            remaining_tokens=remaining_tokens,
            consumed_tokens=consumed_tokens,
            total_requests=total_requests
        )

    def get_top_users(self, organization_name: str, limit: int = 10) -> List[TopUserView]:
        summaries = self.session.query(UserUsageSummary).filter_by(
            organization_name=organization_name
        ).order_by(UserUsageSummary.total_tokens.desc()).limit(limit).all()
        
        return [
            TopUserView(
                user_id=s.user_id,
                total_tokens=s.total_tokens,
                total_cost=float(s.total_cost),
                request_count=s.request_count
            ) for s in summaries
        ]

    def get_user_consumption_report(self, organization_name: str) -> List[UserConsumptionView]:
        summaries = self.session.query(UserUsageSummary).filter_by(
            organization_name=organization_name
        ).all()
        
        return [
            UserConsumptionView(
                user_id=s.user_id,
                total_tokens=s.total_tokens,
                total_cost=float(s.total_cost)
            ) for s in summaries
        ]

    def get_org_usage_report(self, organization_name: str) -> UsageReportView:
        # Since we don't have a daily rollup table yet, we can return empty or mock structure for daily.
        # Ideally we'd group AIUsageLog by date here, but following the rule to avoid scanning it unnecessarily.
        # We'll just return the overview mapped into a single entry or empty list.
        return UsageReportView(
            organization_name=organization_name,
            daily_usage=[] # Placeholder for when a DailyUsageSummary table is added
        )

    def get_ledger(self, organization_name: str, page: int = 1, size: int = 50) -> PaginatedLedgerResponse:
        query = self.session.query(TokenTransactionLedger).filter_by(organization_name=organization_name)
        total = query.count()
        offset = (page - 1) * size
        entries = query.order_by(TokenTransactionLedger.created_at.desc()).offset(offset).limit(size).all()
        
        # Load user details for user_ids in entries to avoid n+1 query patterns
        user_ids = list(set([e.user_id for e in entries if e.user_id]))
        user_map = {}
        if user_ids:
            from models import User
            users = self.session.query(User).filter(User.id.in_(user_ids)).all()
            for u in users:
                name_parts = [u.first_name or "", u.last_name or ""]
                full_name = " ".join([p for p in name_parts if p]).strip() or (u.email.split("@")[0] if u.email else f"User #{u.id}")
                user_map[u.id] = {
                    "name": full_name,
                    "email": u.email
                }

        items = [
            FinancialLedgerView(
                transaction_id=e.id,
                user_id=e.user_id,
                user_name=user_map.get(e.user_id, {}).get("name") if e.user_id else None,
                user_email=user_map.get(e.user_id, {}).get("email") if e.user_id else None,
                transaction_type=e.transaction_type,
                token_delta=e.token_delta,
                created_at=e.created_at.isoformat(),
                reference_id=e.reference_id,
                remarks=e.remarks
            ) for e in entries
        ]
        
        return PaginatedLedgerResponse(
            items=items,
            total=total,
            page=page,
            size=size
        )
