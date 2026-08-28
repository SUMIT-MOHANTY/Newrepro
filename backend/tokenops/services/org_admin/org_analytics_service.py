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
        from models import AIUsageLog
        from tokenops.schemas.orgadmin import DailyUsageView
        from sqlalchemy import func

        # Query AIUsageLog grouped by date
        usage_by_day = self.session.query(
            func.date(AIUsageLog.created_at).label("day"),
            func.sum((AIUsageLog.prompt_tokens or 0) + (AIUsageLog.completion_tokens or 0)).label("total_tokens"),
            func.count(AIUsageLog.id).label("total_requests")
        ).filter(
            func.lower(AIUsageLog.organization_name) == organization_name.lower()
        ).group_by(
            func.date(AIUsageLog.created_at)
        ).order_by(
            func.date(AIUsageLog.created_at).desc()
        ).limit(30).all()

        daily_list = [
            DailyUsageView(
                date=row.day,
                tokens=int(row.total_tokens or 0),
                requests=int(row.total_requests or 0)
            ) for row in usage_by_day
        ]

        return UsageReportView(
            organization_name=organization_name,
            daily_usage=daily_list
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

        import re

        def _extract_payg_cost(remarks: str | None) -> float | None:
            if not remarks:
                return None
            match = re.search(r"Cost:\s*\$([0-9.]+)", remarks)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, TypeError):
                    return None
            return None

        items = [
            FinancialLedgerView(
                transaction_id=e.id,
                user_id=e.user_id,
                user_name=user_map.get(e.user_id, {}).get("name") if e.user_id else None,
                user_email=user_map.get(e.user_id, {}).get("email") if e.user_id else None,
                transaction_type=e.transaction_type,
                token_delta=e.token_delta,
                balance_after=e.balance_after,
                payg_cost_usd=_extract_payg_cost(e.remarks),
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
