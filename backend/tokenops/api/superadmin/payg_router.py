from fastapi import APIRouter, Depends, HTTPException
from tokenops.schemas.superadmin import BaseAPIResponse, PAYGRequestView, PAYGDecisionRequest
from tokenops.services.admin.admin_governance_service import AdminGovernanceService
from .dependencies import verify_super_admin, get_admin_governance_service
from models import User

router = APIRouter(tags=["Super Admin PAYG Governance"])

@router.get("/requests", response_model=BaseAPIResponse)
def get_payg_requests(
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        reqs = gov_service.get_payg_requests()
        data = [
            PAYGRequestView(
                id=r.id,
                organization_name=r.organization_name,
                status=r.status,
                requested_by=r.requested_by,
                created_at=r.created_at.isoformat() if r.created_at else ""
            ) for r in reqs
        ]
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/approve", response_model=BaseAPIResponse)
def approve_payg(
    request: PAYGDecisionRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.handle_payg_request(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            approve=True,
            remarks=request.remarks
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/reject", response_model=BaseAPIResponse)
def reject_payg(
    request: PAYGDecisionRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.handle_payg_request(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            approve=False,
            remarks=request.remarks
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/suspend", response_model=BaseAPIResponse)
def suspend_payg(
    request: PAYGDecisionRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.suspend_payg(
            admin_user_id=current_user.id,
            organization_name=request.organization_name
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.get("/quota-requests", response_model=BaseAPIResponse)
def list_quota_requests(
    status: str = None,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        reqs = gov_service.get_quota_requests(status=status)
        data = [
            {
                "id": r.id,
                "organization_name": r.organization_name,
                "organization_id": r.organization_id,
                "request_type": r.request_type.value if hasattr(r.request_type, "value") else str(r.request_type),
                "requested_tokens": r.requested_tokens,
                "requested_by": r.requested_by,
                "requester_email": r.requester.email if r.requester else None,
                "requester_name": f"{r.requester.first_name or ''} {r.requester.last_name or ''}".strip() or (r.requester.email.split('@')[0] if r.requester and r.requester.email else f"User #{r.requested_by}"),
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "remarks": r.remarks,
                "admin_notes": r.admin_notes,
                "approved_by": r.approved_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            }
            for r in reqs
        ]
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.post("/quota-requests/{request_id}/approve", response_model=BaseAPIResponse)
def approve_quota_request(
    request_id: int,
    payload: dict = None,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        remarks = payload.get("remarks") if payload else None
        req = gov_service.handle_quota_request(
            admin_user_id=current_user.id,
            request_id=request_id,
            approve=True,
            remarks=remarks
        )
        return BaseAPIResponse(success=True, data={"id": req.id, "status": "APPROVED"})
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.post("/quota-requests/{request_id}/reject", response_model=BaseAPIResponse)
def reject_quota_request(
    request_id: int,
    payload: dict = None,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        remarks = payload.get("remarks") if payload else None
        req = gov_service.handle_quota_request(
            admin_user_id=current_user.id,
            request_id=request_id,
            approve=False,
            remarks=remarks
        )
        return BaseAPIResponse(success=True, data={"id": req.id, "status": "REJECTED"})
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


# ── PAYG Spending Limits (Option C) ──────────────────────────────────────────

from tokenops.schemas.superadmin import PAYGLimitsUpdateRequest, GenerateInvoiceRequest, GenerateMonthlyInvoicesRequest, PAYGInvoiceView
from .dependencies import get_payg_invoice_service
from tokenops.services.payg_invoice_service import PAYGInvoiceService
import json

@router.post("/limits", response_model=BaseAPIResponse)
def update_payg_limits(
    request: PAYGLimitsUpdateRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        kwargs = {}
        if "soft_limit_usd" in request.model_fields_set:
            kwargs["soft_limit_usd"] = request.soft_limit_usd
        if "hard_limit_usd" in request.model_fields_set:
            kwargs["hard_limit_usd"] = request.hard_limit_usd
        if "billing_email" in request.model_fields_set:
            kwargs["billing_email"] = request.billing_email

        wallet = gov_service.set_payg_limits(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            **kwargs
        )
        return BaseAPIResponse(
            success=True,
            data={
                "organization_name": wallet.organization_name,
                "payg_enabled": bool(wallet.payg_enabled),
                "soft_limit_usd": float(wallet.payg_soft_limit_usd) if wallet.payg_soft_limit_usd else None,
                "hard_limit_usd": float(wallet.payg_hard_limit_usd) if wallet.payg_hard_limit_usd else None,
                "current_spend_usd": float(wallet.payg_current_spend_usd or 0.0),
                "billing_email": wallet.payg_billing_email
            }
        )
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


# ── PAYG Invoices ─────────────────────────────────────────────────────────────

@router.post("/invoices/generate", response_model=BaseAPIResponse)
def generate_invoice(
    request: GenerateInvoiceRequest,
    current_user: User = Depends(verify_super_admin),
    invoice_service: PAYGInvoiceService = Depends(get_payg_invoice_service)
):
    try:
        inv = invoice_service.generate_invoice(
            organization_name=request.organization_name,
            billing_month=request.billing_month,
            force_regenerate=bool(request.force_regenerate),
            recipient_email=request.recipient_email,
            send_email=bool(request.send_email)
        )
        line_items = json.loads(inv.line_items) if inv.line_items else []
        data = PAYGInvoiceView(
            id=inv.id,
            organization_name=inv.organization_name,
            organization_id=inv.organization_id,
            billing_month=inv.billing_month,
            total_tokens=inv.total_tokens,
            prompt_tokens=inv.prompt_tokens,
            completion_tokens=inv.completion_tokens,
            input_cost=float(inv.input_cost),
            output_cost=float(inv.output_cost),
            total_cost=float(inv.total_cost),
            line_items=line_items,
            invoice_status=inv.invoice_status,
            recipient_email=inv.recipient_email,
            generated_at=inv.generated_at.isoformat(),
            paid_at=inv.paid_at.isoformat() if inv.paid_at else None
        )
        return BaseAPIResponse(success=True, data=data)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "INVOICE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.post("/invoices/generate-monthly", response_model=BaseAPIResponse)
def generate_monthly_invoices(
    request: GenerateMonthlyInvoicesRequest = None,
    current_user: User = Depends(verify_super_admin),
    invoice_service: PAYGInvoiceService = Depends(get_payg_invoice_service)
):
    try:
        month = request.billing_month if request else None
        invoices = invoice_service.generate_all_monthly_invoices(billing_month=month)
        data = [
            {
                "id": inv.id,
                "organization_name": inv.organization_name,
                "billing_month": inv.billing_month,
                "total_tokens": inv.total_tokens,
                "total_cost": float(inv.total_cost),
                "invoice_status": inv.invoice_status,
                "recipient_email": inv.recipient_email,
                "generated_at": inv.generated_at.isoformat()
            }
            for inv in invoices
        ]
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.get("/invoices", response_model=BaseAPIResponse)
def list_invoices(
    organization_name: str = None,
    billing_month: str = None,
    page: int = 1,
    size: int = 50,
    current_user: User = Depends(verify_super_admin),
    invoice_service: PAYGInvoiceService = Depends(get_payg_invoice_service)
):
    try:
        items, total = invoice_service.get_invoices(
            organization_name=organization_name,
            billing_month=billing_month,
            page=page,
            size=size
        )
        data = [
            {
                "id": inv.id,
                "organization_name": inv.organization_name,
                "organization_id": inv.organization_id,
                "billing_month": inv.billing_month,
                "total_tokens": inv.total_tokens,
                "prompt_tokens": inv.prompt_tokens,
                "completion_tokens": inv.completion_tokens,
                "input_cost": float(inv.input_cost),
                "output_cost": float(inv.output_cost),
                "total_cost": float(inv.total_cost),
                "line_items": json.loads(inv.line_items) if inv.line_items else [],
                "invoice_status": inv.invoice_status,
                "recipient_email": inv.recipient_email,
                "generated_at": inv.generated_at.isoformat(),
                "paid_at": inv.paid_at.isoformat() if inv.paid_at else None
            }
            for inv in items
        ]
        return BaseAPIResponse(success=True, data={"items": data, "total": total, "page": page, "size": size})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.get("/invoices/{invoice_id}", response_model=BaseAPIResponse)
def get_invoice_detail(
    invoice_id: int,
    current_user: User = Depends(verify_super_admin),
    invoice_service: PAYGInvoiceService = Depends(get_payg_invoice_service)
):
    try:
        inv = invoice_service.get_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        data = {
            "id": inv.id,
            "organization_name": inv.organization_name,
            "organization_id": inv.organization_id,
            "billing_month": inv.billing_month,
            "total_tokens": inv.total_tokens,
            "prompt_tokens": inv.prompt_tokens,
            "completion_tokens": inv.completion_tokens,
            "input_cost": float(inv.input_cost),
            "output_cost": float(inv.output_cost),
            "total_cost": float(inv.total_cost),
            "line_items": json.loads(inv.line_items) if inv.line_items else [],
            "invoice_status": inv.invoice_status,
            "recipient_email": inv.recipient_email,
            "generated_at": inv.generated_at.isoformat(),
            "paid_at": inv.paid_at.isoformat() if inv.paid_at else None
        }
        return BaseAPIResponse(success=True, data=data)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "INVOICE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})


@router.post("/invoices/{invoice_id}/send-email", response_model=BaseAPIResponse)
def send_invoice_email(
    invoice_id: int,
    payload: dict = None,
    current_user: User = Depends(verify_super_admin),
    invoice_service: PAYGInvoiceService = Depends(get_payg_invoice_service)
):
    try:
        inv = invoice_service.get_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        email = payload.get("email") if payload else None
        sent = invoice_service.send_invoice_email(inv, recipient_email=email)
        return BaseAPIResponse(success=True, data={"sent": sent, "recipient_email": email or inv.recipient_email})
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "INVOICE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

