from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from tokenops.models.organization import Organization
from tokenops.models.token_wallet import OrganizationWallet
from tokenops.models.summary import OrganizationUsageSummary, UserUsageSummary
from tokenops.models.quota_request import TokenQuotaRequest
from tokenops.models.ledger import TokenTransactionLedger
from models import AIUsageLog, User
from tokenops.schemas.orgadmin import FinancialLedgerView, PaginatedLedgerResponse
from tokenops.schemas.superadmin import (
    AnalyticsOverview, OrganizationAnalytics, DailyUsageView, TopUserView,
    TrendPoint, UsageTrendsResponse, ModelUsageView,
    TopOrganizationItem, TopOrganizationsResponse,
    AlertItem, OperationalAlertsResponse
)

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
        # 1. Wallet Stats
        wallet_query = self.session.query(OrganizationWallet)
        
        if organization:
            wallet_query = wallet_query.filter(OrganizationWallet.organization_name == organization)
        if billing_mode:
            payg = billing_mode.lower() == "payg"
            wallet_query = wallet_query.filter(OrganizationWallet.payg_enabled == payg)
            
        total_orgs = self.session.query(Organization).count() if not organization else wallet_query.count()
        payg_orgs = wallet_query.filter(OrganizationWallet.payg_enabled == True).count()
        prepaid_orgs = max(0, total_orgs - payg_orgs)
        blocked_orgs = wallet_query.filter(OrganizationWallet.is_blocked == True).count()
        low_balance_orgs = wallet_query.filter(
            OrganizationWallet.payg_enabled == False,
            OrganizationWallet.remaining_tokens < 100000
        ).count()
        
        # PAYG Spend & Hard Limit Breaches
        payg_limit_breaches = 0
        total_payg_spend = 0.0
        for w in wallet_query.filter(OrganizationWallet.payg_enabled == True).all():
            spend = float(w.payg_current_spend_usd or 0.0)
            total_payg_spend += spend
            if w.payg_hard_limit_usd is not None and spend >= float(w.payg_hard_limit_usd):
                payg_limit_breaches += 1
        
        # 2. Pending Quota Requests
        pending_quota_requests = self.session.query(TokenQuotaRequest).filter(
            TokenQuotaRequest.status == "REQUESTED"
        ).count()
        
        # 3. Usage Stats from OrganizationUsageSummary
        usage_query = self.session.query(
            func.sum(OrganizationUsageSummary.total_prompt_tokens + OrganizationUsageSummary.total_completion_tokens).label('total_tokens'),
            func.sum(OrganizationUsageSummary.request_count).label('total_requests'),
            func.sum(OrganizationUsageSummary.total_cost).label('total_cost')
        )
        
        if organization:
            usage_query = usage_query.filter(OrganizationUsageSummary.organization_name == organization)
            
        result = usage_query.first()
        total_tokens = int(result.total_tokens or 0)
        total_requests = int(result.total_requests or 0)
        total_historical_cost = round(float(result.total_cost or 0.0), 2)
        
        return AnalyticsOverview(
            total_organizations=total_orgs,
            prepaid_organizations=prepaid_orgs,
            payg_organizations=payg_orgs,
            blocked_organizations=blocked_orgs,
            total_tokens_consumed=total_tokens,
            total_requests=total_requests,
            total_historical_cost=total_historical_cost,
            low_balance_organizations=low_balance_orgs,
            pending_quota_requests=pending_quota_requests,
            payg_limit_breaches=payg_limit_breaches,
            total_payg_current_spend_usd=round(total_payg_spend, 2)
        )

    def get_trends(self, range_str: str = "30d") -> UsageTrendsResponse:
        """
        Calculates daily time-series usage trends (7d, 30d, 90d).
        Every day in the interval is returned; zero-activity days are zero-filled.
        """
        range_str_clean = (range_str or "30d").lower()
        if range_str_clean == "7d":
            num_days = 7
        elif range_str_clean == "90d":
            num_days = 90
        else:
            num_days = 30
            range_str_clean = "30d"

        today = datetime.utcnow().date()
        start_date = today - timedelta(days=num_days - 1)
        start_dt = datetime.combine(start_date, datetime.min.time())

        # Query AIUsageLog grouped by date
        results = self.session.query(
            func.date(AIUsageLog.created_at).label("day"),
            func.sum(AIUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(AIUsageLog.completion_tokens).label("completion_tokens"),
            func.count(AIUsageLog.id).label("request_count"),
            func.sum(AIUsageLog.cost).label("cost")
        ).filter(
            AIUsageLog.created_at >= start_dt
        ).group_by(
            func.date(AIUsageLog.created_at)
        ).all()

        # Initialize full calendar lookup with zeroes
        day_map: Dict[str, Dict[str, Any]] = {}
        curr = start_date
        while curr <= today:
            d_str = curr.isoformat()
            day_map[d_str] = {
                "date": d_str,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "request_count": 0,
                "cost_usd": 0.0
            }
            curr += timedelta(days=1)

        # Overlay aggregated results
        for row in results:
            if not row.day:
                continue
            day_key = str(row.day)[:10]
            if day_key in day_map:
                p_toks = int(row.prompt_tokens or 0)
                c_toks = int(row.completion_tokens or 0)
                day_map[day_key] = {
                    "date": day_key,
                    "total_tokens": p_toks + c_toks,
                    "prompt_tokens": p_toks,
                    "completion_tokens": c_toks,
                    "request_count": int(row.request_count or 0),
                    "cost_usd": round(float(row.cost or 0.0), 4)
                }

        points = [TrendPoint(**day_map[k]) for k in sorted(day_map.keys())]

        return UsageTrendsResponse(
            range=range_str_clean,
            from_date=start_date.isoformat(),
            to_date=today.isoformat(),
            points=points
        )

    def get_model_usage(self) -> List[ModelUsageView]:
        """
        Calculates platform-wide AI token consumption and cost per model.
        """
        results = self.session.query(
            AIUsageLog.model,
            func.sum(AIUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(AIUsageLog.completion_tokens).label("completion_tokens"),
            func.count(AIUsageLog.id).label("request_count"),
            func.sum(AIUsageLog.cost).label("cost")
        ).filter(
            AIUsageLog.model.isnot(None)
        ).group_by(
            AIUsageLog.model
        ).all()

        total_platform_tokens = sum([
            int((r.prompt_tokens or 0) + (r.completion_tokens or 0)) for r in results
        ])

        models_list: List[ModelUsageView] = []
        for r in results:
            m_name = str(r.model or "unknown")
            p_toks = int(r.prompt_tokens or 0)
            c_toks = int(r.completion_tokens or 0)
            t_toks = p_toks + c_toks
            cnt = int(r.request_count or 0)
            c_usd = round(float(r.cost or 0.0), 4)
            pct = round((t_toks / total_platform_tokens * 100.0), 1) if total_platform_tokens > 0 else 0.0

            models_list.append(ModelUsageView(
                model=m_name,
                total_tokens=t_toks,
                prompt_tokens=p_toks,
                completion_tokens=c_toks,
                request_count=cnt,
                cost_usd=c_usd,
                percentage=pct
            ))

        models_list.sort(key=lambda m: m.total_tokens, reverse=True)
        return models_list

    def get_top_organizations(self, limit: int = 10) -> TopOrganizationsResponse:
        """
        Returns top organizations ranked by token consumption and by cost.
        """
        summaries = self.session.query(OrganizationUsageSummary).all()
        wallets = {w.organization_name: w for w in self.session.query(OrganizationWallet).all()}

        items: List[TopOrganizationItem] = []
        for s in summaries:
            w = wallets.get(s.organization_name)
            is_payg = bool(w.payg_enabled) if w else False
            is_blocked = bool(w.is_blocked) if w else False
            remaining = int(w.remaining_tokens or 0) if w else 0
            payg_spend = round(float(w.payg_current_spend_usd or 0.0), 2) if w else 0.0
            tot_tokens = int(s.total_tokens or (s.total_prompt_tokens + s.total_completion_tokens) or 0)
            reqs = int(s.request_count or 0)
            tot_cost = round(float(s.total_cost or 0.0), 2)

            items.append(TopOrganizationItem(
                organization_name=s.organization_name,
                organization_id=s.organization_id or (w.organization_id if w else None),
                billing_mode="PAYG" if is_payg else "Prepaid",
                total_tokens=tot_tokens,
                request_count=reqs,
                total_cost_usd=tot_cost,
                payg_spend_usd=payg_spend,
                remaining_tokens=remaining,
                is_blocked=is_blocked
            ))

        by_tokens = sorted(items, key=lambda x: x.total_tokens, reverse=True)[:limit]
        by_cost = sorted(items, key=lambda x: x.total_cost_usd, reverse=True)[:limit]

        return TopOrganizationsResponse(
            by_tokens=by_tokens,
            by_cost=by_cost
        )

    def get_operational_alerts(self) -> OperationalAlertsResponse:
        """
        Derives operational health exceptions and alerts dynamically from wallets and requests.
        """
        critical_alerts: List[AlertItem] = []
        warning_alerts: List[AlertItem] = []
        action_required: List[AlertItem] = []

        all_wallets = self.session.query(OrganizationWallet).all()
        for w in all_wallets:
            # 1. Blocked Orgs (Critical)
            if w.is_blocked:
                critical_alerts.append(AlertItem(
                    organization_name=w.organization_name,
                    organization_id=w.organization_id,
                    alert_type="BLOCKED",
                    severity="critical",
                    message=f"Organization '{w.organization_name}' is administratively BLOCKED."
                ))

            # 2. PAYG Limit Monitoring
            if w.payg_enabled:
                spend = float(w.payg_current_spend_usd or 0.0)
                hard_limit = float(w.payg_hard_limit_usd) if w.payg_hard_limit_usd is not None else None
                soft_limit = float(w.payg_soft_limit_usd) if w.payg_soft_limit_usd is not None else None

                if hard_limit is not None and spend >= hard_limit:
                    critical_alerts.append(AlertItem(
                        organization_name=w.organization_name,
                        organization_id=w.organization_id,
                        alert_type="HARD_LIMIT_BREACH",
                        severity="critical",
                        message=f"PAYG Hard Limit reached/exceeded (${spend:.2f} / ${hard_limit:.2f}).",
                        metric_value=f"${spend:.2f} / ${hard_limit:.2f}"
                    ))
                elif soft_limit is not None and spend >= (soft_limit * 0.8):
                    warning_alerts.append(AlertItem(
                        organization_name=w.organization_name,
                        organization_id=w.organization_id,
                        alert_type="SOFT_LIMIT_APPROACHING",
                        severity="warning",
                        message=f"PAYG Soft Limit warning threshold exceeded (${spend:.2f} / ${soft_limit:.2f}).",
                        metric_value=f"${spend:.2f} / ${soft_limit:.2f}"
                    ))
            else:
                # 3. Prepaid Low Balance Warning
                remaining = int(w.remaining_tokens or 0)
                if remaining < 100000 and not w.is_blocked:
                    warning_alerts.append(AlertItem(
                        organization_name=w.organization_name,
                        organization_id=w.organization_id,
                        alert_type="LOW_BALANCE",
                        severity="warning",
                        message=f"Low prepaid balance ({remaining:,} tokens remaining).",
                        metric_value=f"{remaining:,} tokens"
                    ))

        # 4. Pending Quota Requests
        quota_reqs = self.session.query(TokenQuotaRequest).filter(
            TokenQuotaRequest.status == "REQUESTED"
        ).all()
        for q in quota_reqs:
            action_required.append(AlertItem(
                organization_name=q.organization_name,
                organization_id=q.organization_id,
                alert_type="PENDING_QUOTA",
                severity="info",
                message=f"Pending quota request for {int(q.requested_tokens or 0):,} tokens.",
                metric_value=f"{int(q.requested_tokens or 0):,} tokens",
                created_at=q.created_at.isoformat() if q.created_at else None
            ))

        total = len(critical_alerts) + len(warning_alerts) + len(action_required)

        return OperationalAlertsResponse(
            critical=critical_alerts,
            warning=warning_alerts,
            action_required=action_required,
            total_alerts=total
        )

    def get_organization_analytics(self, organization_name: str) -> OrganizationAnalytics:
        wallet = self.session.query(OrganizationWallet).filter_by(organization_name=organization_name).first()
        usage_summary = self.session.query(OrganizationUsageSummary).filter_by(organization_name=organization_name).first()
        
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=6)
        daily_results = self.session.query(
            func.date(AIUsageLog.created_at).label("day"),
            func.sum(AIUsageLog.prompt_tokens + AIUsageLog.completion_tokens).label("tokens"),
            func.count(AIUsageLog.id).label("requests")
        ).filter(
            AIUsageLog.organization_name == organization_name,
            AIUsageLog.created_at >= datetime.combine(start_date, datetime.min.time())
        ).group_by(
            func.date(AIUsageLog.created_at)
        ).all()
        
        day_map = {}
        curr = start_date
        while curr <= today:
            day_map[curr.isoformat()] = {"date": curr.isoformat(), "tokens": 0, "requests": 0}
            curr += timedelta(days=1)
            
        for r in daily_results:
            if r.day:
                k = str(r.day)[:10]
                if k in day_map:
                    day_map[k] = {
                        "date": k,
                        "tokens": int(r.tokens or 0),
                        "requests": int(r.requests or 0)
                    }
                    
        daily_usage = [DailyUsageView(**day_map[k]) for k in sorted(day_map.keys())]
        
        top_user_summaries = (
            self.session.query(UserUsageSummary, User)
            .outerjoin(User, UserUsageSummary.user_id == User.id)
            .filter(UserUsageSummary.organization_name == organization_name)
            .order_by(UserUsageSummary.total_tokens.desc())
            .limit(5)
            .all()
        )
        
        top_users = []
        for summary, user in top_user_summaries:
            name = None
            email = None
            if user:
                full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                name = full_name if full_name else (user.email or f"User #{summary.user_id}")
                email = user.email
            else:
                name = f"User #{summary.user_id}"
            top_users.append(
                TopUserView(
                    user_id=summary.user_id,
                    user_name=name,
                    email=email,
                    tokens=int(summary.total_tokens or 0)
                )
            )
        
        return OrganizationAnalytics(
            organization_name=organization_name,
            daily_usage=daily_usage,
            top_users=top_users,
            token_burn=usage_summary.total_tokens if usage_summary else 0,
            remaining_balance=wallet.remaining_tokens if wallet else 0,
            total_historical_cost=float(usage_summary.total_cost) if usage_summary else 0.0
        )

    def get_ledger(
        self,
        organization_name: Optional[str] = None,
        page: int = 1,
        size: int = 10,
        transaction_type: Optional[str] = None,
        purpose: Optional[str] = None,
        search: Optional[str] = None
    ) -> PaginatedLedgerResponse:
        import re
        from sqlalchemy import or_

        query = self.session.query(TokenTransactionLedger)

        if organization_name and organization_name.strip() and organization_name.strip().upper() != "ALL":
            query = query.filter(func.lower(TokenTransactionLedger.organization_name) == organization_name.strip().lower())

        if transaction_type and transaction_type != "ALL":
            if transaction_type == "INFLOW":
                query = query.filter(TokenTransactionLedger.token_delta > 0)
            elif transaction_type == "OUTFLOW":
                query = query.filter(TokenTransactionLedger.token_delta < 0)
            elif transaction_type == "ALLOCATION":
                query = query.filter(TokenTransactionLedger.transaction_type.in_(["ALLOCATION", "PURCHASE", "REALLOCATION"]))
            else:
                query = query.filter(TokenTransactionLedger.transaction_type == transaction_type)

        if purpose and purpose.strip() and purpose.strip().upper() != "ALL":
            p_val = purpose.strip()
            query = query.filter(
                or_(
                    TokenTransactionLedger.purpose.ilike(f"%{p_val}%"),
                    TokenTransactionLedger.remarks.ilike(f"%{p_val}%")
                )
            )

        if search and search.strip():
            s = f"%{search.strip()}%"
            query = query.outerjoin(User, TokenTransactionLedger.user_id == User.id).filter(
                or_(
                    TokenTransactionLedger.organization_name.ilike(s),
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

        # Load user details
        user_ids = list(set([e.user_id for e in entries if e.user_id]))
        user_map = {}
        if user_ids:
            users = self.session.query(User).filter(User.id.in_(user_ids)).all()
            for u in users:
                name_parts = [u.first_name or "", u.last_name or ""]
                full_name = " ".join([p for p in name_parts if p]).strip() or (u.email.split("@")[0] if u.email else f"User #{u.id}")
                user_map[u.id] = {
                    "name": full_name,
                    "email": u.email
                }

        # Batch resolve project names if missing
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

        # Cache reference prices for organizations in current batch
        org_names = list(set([e.organization_name for e in entries if e.organization_name]))
        ref_price_map = {}
        if org_names:
            wallets = self.session.query(OrganizationWallet).filter(OrganizationWallet.organization_name.in_(org_names)).all()
            for w in wallets:
                ref_price_map[w.organization_name] = float(getattr(w, "reference_price", 0.000007) or 0.000007)

        def _resolve_purpose(e: TokenTransactionLedger) -> str:
            if getattr(e, "purpose", None):
                return e.purpose
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
            org_ref_price = ref_price_map.get(e.organization_name, 0.000007)
            cost_usd = payg_cost if payg_cost is not None else round(abs_delta * org_ref_price, 6)

            p_tok = getattr(e, "project_token", None)
            p_name = getattr(e, "project_name", None) or (project_map.get(p_tok) if p_tok else None)

            seq_tx_id = max(1, total - (offset + idx))

            items.append(
                FinancialLedgerView(
                    transaction_id=seq_tx_id,
                    global_transaction_id=e.id,
                    organization_name=e.organization_name,
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

