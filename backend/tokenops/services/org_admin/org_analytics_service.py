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

    def get_ledger(
        self,
        organization_name: str,
        page: int = 1,
        size: int = 10,
        transaction_type: str | None = None,
        search: str | None = None
    ) -> PaginatedLedgerResponse:
        from sqlalchemy import or_
        from models import User
        query = self.session.query(TokenTransactionLedger).filter(TokenTransactionLedger.organization_name == organization_name)

        if transaction_type and transaction_type != "ALL":
            if transaction_type == "INFLOW":
                query = query.filter(TokenTransactionLedger.token_delta > 0)
            elif transaction_type == "OUTFLOW":
                query = query.filter(TokenTransactionLedger.token_delta < 0)
            elif transaction_type == "ALLOCATION":
                query = query.filter(TokenTransactionLedger.transaction_type.in_(["ALLOCATION", "PURCHASE", "REALLOCATION"]))
            else:
                query = query.filter(TokenTransactionLedger.transaction_type == transaction_type)

        if search and search.strip():
            s = f"%{search.strip()}%"
            query = query.outerjoin(User, TokenTransactionLedger.user_id == User.id).filter(
                or_(
                    TokenTransactionLedger.remarks.ilike(s),
                    TokenTransactionLedger.reference_id.ilike(s),
                    TokenTransactionLedger.purpose.ilike(s),
                    TokenTransactionLedger.project_name.ilike(s),
                    User.first_name.ilike(s),
                    User.last_name.ilike(s),
                    User.email.ilike(s)
                )
            )

        total = query.count()
        offset = (page - 1) * size
        entries = query.order_by(TokenTransactionLedger.created_at.desc(), TokenTransactionLedger.id.desc()).offset(offset).limit(size).all()
        
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

        # Batch resolve project names if missing from ledger entries
        proj_tokens = list(set([e.project_token for e in entries if getattr(e, "project_token", None) and not getattr(e, "project_name", None)]))
        project_map = {}
        if proj_tokens:
            try:
                from models import GovernanceResponse, ShareProject
                govs = self.session.query(GovernanceResponse.project_token, GovernanceResponse.project_name).filter(
                    GovernanceResponse.project_token.in_(proj_tokens)
                ).all()
                for pt, pn in govs:
                    if pn:
                        project_map[pt] = pn
                
                # Also check ShareProjects for any remaining unresolved
                remaining_tokens = [t for t in proj_tokens if t not in project_map]
                if remaining_tokens:
                    sps = self.session.query(ShareProject.project_token, ShareProject.project_name).filter(
                        ShareProject.project_token.in_(remaining_tokens)
                    ).all()
                    for pt, pn in sps:
                        if pn:
                            project_map[pt] = pn
            except Exception:
                pass

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

        # Fetch org reference price for calculating USD cost equivalent
        wallet = self.session.query(OrganizationWallet).filter_by(organization_name=organization_name).first()
        reference_price = float(getattr(wallet, "reference_price", 0.000007) or 0.000007)

        def _resolve_purpose(e: TokenTransactionLedger) -> str:
            if getattr(e, "purpose", None):
                return e.purpose
            # Graceful fallback derivation for historical ledger rows
            ttype = e.transaction_type or ""
            if ttype == "ALLOCATION":
                return "Admin Quota Allocation"
            elif ttype == "PURCHASE":
                return "Token Pack Purchase"
            elif ttype == "REALLOCATION":
                return "User Wallet Reallocation"
            elif ttype == "REVOCATION":
                return "Quota Revocation"
            elif ttype == "MANUAL_ADJUSTMENT":
                return "Manual Balance Adjustment"
            elif ttype in ("AI_CONSUMPTION", "PAYG_USAGE"):
                rem = e.remarks or ""
                if "Screening" in rem:
                    return "Requirement Screening"
                elif "Gap" in rem:
                    return "Codebase Gap Analysis"
                elif "Test" in rem:
                    return "Test Case Generation"
                elif "Analyze" in rem or "Analysis" in rem:
                    return "BRD Analysis & Architecture"
                elif "PR" in rem:
                    return "PR Description Generation"
                elif "Agent" in rem:
                    return "Autonomous Coding Agent"
                return "AI Consumption"
            return ttype.replace("_", " ").title()

        items = []
        for idx, e in enumerate(entries):
            payg_cost = _extract_payg_cost(e.remarks)
            abs_delta = abs(e.token_delta)
            cost_usd = payg_cost if payg_cost is not None else round(abs_delta * reference_price, 6)
            
            p_tok = getattr(e, "project_token", None)
            p_name = getattr(e, "project_name", None) or (project_map.get(p_tok) if p_tok else None)

            # Organization-scoped sequential ID (#1 = oldest tx for this org, #total = newest tx)
            org_tx_id = max(1, total - (offset + idx))

            items.append(
                FinancialLedgerView(
                    transaction_id=org_tx_id,
                    global_transaction_id=e.id,
                    user_id=e.user_id,
                    user_name=user_map.get(e.user_id, {}).get("name") if e.user_id else None,
                    user_email=user_map.get(e.user_id, {}).get("email") if e.user_id else None,
                    transaction_type=e.transaction_type,
                    purpose=_resolve_purpose(e),
                    project_token=p_tok,
                    project_name=p_name,
                    token_delta=e.token_delta,
                    balance_after=e.balance_after,
                    cost_usd=cost_usd,
                    payg_cost_usd=payg_cost,
                    created_at=(e.created_at.isoformat() + "Z") if e.created_at else None,
                    reference_id=e.reference_id,
                    remarks=e.remarks
                )
            )
        
        return PaginatedLedgerResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            total_pages=max(1, (total + size - 1) // size) if total > 0 else 1
        )
