"""
Agent Billing Service
Bridges real-time LLM token execution events from Agent Runtime containers
to the TokenOps financial ledger, wallet governance, and AIUsageLog auditing.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import func

from app.core.database import SessionLocal
import models

logger = logging.getLogger(__name__)


def record_agent_llm_usage(
    payload: Dict[str, Any],
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
    event_uid: Optional[str] = None,
    user_id: Optional[int] = None,
) -> bool:
    """
    Process token usage and calculate costs for an LLM call made by a subagent/worker agent.

    Guarantees:
      1. Strictly idempotent via TokenOps IdempotencyKey using event_uid as request_id.
      2. Safe isolation: uses a dedicated database session with full exception absorption.
      3. Authoritative TokenOps post_execute invocation:
         - Deducts from UserTokenWallet if organization is Prepaid.
         - Accrues to payg_current_spend_usd if organization is PAYG.
         - Appends auditable transaction to TokenTransactionLedger.
         - Writes an immutable record to AIUsageLog (ai_usage_logs table).
         - Increments tenant and user rollup usage summaries.
    """
    if not isinstance(payload, dict):
        return False

    prompt_tokens = int(payload.get("input_tokens") or payload.get("prompt_tokens") or 0)
    completion_tokens = int(payload.get("output_tokens") or payload.get("completion_tokens") or 0)
    total_tokens = int(payload.get("total_tokens") or (prompt_tokens + completion_tokens) or 0)

    # If no tokens were recorded, skip billing
    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
        return False

    model_name = str(payload.get("model") or "claude")
    req_id = str(event_uid or payload.get("event_uid") or f"agent_llm_{uuid.uuid4().hex}")

    # Extract session / task / project from payload if not provided
    sess_id = session_id or payload.get("session_id")
    t_id = task_id or payload.get("task_id")
    p_id = project_id or payload.get("project_id")

    db = SessionLocal()
    try:
        u_id = user_id
        tenant_id = None
        sess = None

        if sess_id:
            try:
                sess = db.query(models.AgentSession).filter(models.AgentSession.id == str(sess_id)).first()
                if sess:
                    u_id = u_id or sess.user_id
                    p_id = p_id or sess.project_id
                    tenant_id = sess.tenant_id
            except Exception:
                pass

        # Check payload user_id
        if u_id is None and payload.get("user_id"):
            try:
                u_id = int(payload.get("user_id"))
            except (ValueError, TypeError):
                pass

        # Fallback resolution from database tables linked to p_id
        if u_id is None and p_id:
            try:
                doc = db.query(models.Document).filter(models.Document.project_token == str(p_id)).first()
                if doc and doc.owner_id:
                    u_id = doc.owner_id
            except Exception:
                pass

        if u_id is None and p_id:
            try:
                gov = db.query(models.GovernanceResponse).filter(models.GovernanceResponse.project_token == str(p_id)).first()
                if gov and gov.owner_id:
                    u_id = gov.owner_id
            except Exception:
                pass

        if u_id is None and p_id:
            try:
                sp = db.query(models.ShareProject).filter(models.ShareProject.project_token == str(p_id)).first()
                if sp and sp.owner_id:
                    u_id = sp.owner_id
            except Exception:
                pass

        if u_id is None and t_id:
            try:
                t_rec = db.query(models.Task).filter(models.Task.task_id == str(t_id)).first()
                if t_rec and getattr(t_rec, "owner_id", None):
                    u_id = t_rec.owner_id
            except Exception:
                pass

        # Resolve organization name
        org_name = None
        if u_id:
            try:
                u_rec = db.query(models.User).filter(models.User.id == u_id).first()
                if u_rec and u_rec.organization_name:
                    org_name = u_rec.organization_name
            except Exception:
                pass

        if not org_name and tenant_id and tenant_id != "default":
            org_name = tenant_id

        if not org_name and p_id:
            try:
                gov = db.query(models.GovernanceResponse).filter(models.GovernanceResponse.project_token == str(p_id)).first()
                if gov and gov.organization_name:
                    org_name = gov.organization_name
            except Exception:
                pass

        from tokenops.services.project_token_resolver import resolve_or_ensure_project_token
        from tokenops.services.tenant_resolver_service import TenantResolverService
        from tokenops.services.tokenops_orchestrator import TokenOpsOrchestrator
        from tokenops.repositories.organization_wallet import OrganizationWalletRepository
        from tokenops.repositories.user_wallet import UserWalletRepository

        resolved_proj_token, resolved_proj_name = resolve_or_ensure_project_token(
            session=db,
            user_id=u_id,
            organization_name=org_name,
            candidate_project_token=p_id,
            candidate_project_name=payload.get("project_name")
        )

        resolver = TenantResolverService(db)
        target_tenant = org_name or resolved_proj_token
        try:
            _, tenant_org = resolver.resolve(target_tenant)
            canonical_tenant_name = tenant_org.name
        except Exception:
            canonical_tenant_name = target_tenant

        if u_id is None and canonical_tenant_name:
            u_fallback = db.query(models.User).filter(
                func.lower(models.User.organization_name) == canonical_tenant_name.lower(),
                models.User.is_active == True
            ).first()
            if u_fallback:
                u_id = u_fallback.id

        # Ensure OrganizationWallet and UserTokenWallet exist so tokens are deducted accurately
        org_wallet_repo = OrganizationWalletRepository(db)
        org_wallet_repo.get_or_create(canonical_tenant_name)

        if u_id:
            user_wallet_repo = UserWalletRepository(db)
            user_wallet_repo.get_user_wallet(u_id, canonical_tenant_name)

        agent_label = (
            payload.get("sub_agent")
            or payload.get("agent_name")
            or payload.get("agent")
            or payload.get("agent_id")
            or "Coding Agent"
        )
        task_label = f"Task: {t_id}" if t_id else "Autonomous Coding"
        purpose = f"Coding Agent: {agent_label} ({task_label})"

        orchestrator = TokenOpsOrchestrator.create(db)
        orchestrator.post_execute(
            user_id=u_id or 0,
            organization_name=canonical_tenant_name,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_id=req_id,
            purpose=purpose,
            project_token=resolved_proj_token,
            project_name=resolved_proj_name,
        )
        logger.info(
            f"[AgentBilling] Billed {prompt_tokens}+{completion_tokens} tokens ({model_name}) "
            f"for tenant '{canonical_tenant_name}' (user: {u_id}, req: {req_id}, purpose: '{purpose}')."
        )
        return True
    except Exception as exc:
        logger.error(f"[AgentBilling] Error processing agent LLM billing for {req_id}: {exc}", exc_info=True)
        return False
    finally:
        db.close()
