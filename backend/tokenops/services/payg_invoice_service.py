"""
TokenOps — PAYG Invoice Generation Service (Option C).

Handles:
- Auditable billing-period aggregation from immutable AIUsageLog entries.
- Snapshotting itemized input/output tokens and historical per-token rates.
- Duplicate invoice prevention via UniqueConstraint (organization_name, billing_month).
- On-demand and scheduled batch monthly invoice generation.
- Automated billing email delivery with itemized breakdowns.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from tokenops.models.payg import PAYGInvoice, InvoiceStatus
from tokenops.models.token_wallet import OrganizationWallet, UserOrganization
from models import AIUsageLog, User, UserOrganizationRole, OrganizationRole
from tokenops.services.tenant_resolver_service import TenantResolverService
from tokenops.services.pricing_service import PricingService
import email_service

logger = logging.getLogger(__name__)


class PAYGInvoiceService:
    def __init__(self, session: Session, pricing_service: PricingService):
        self.session = session
        self.pricing_service = pricing_service
        self.tenant_resolver = TenantResolverService(session)

    def _parse_billing_month(self, billing_month: str) -> Tuple[datetime, datetime]:
        """
        Parses 'YYYY-MM' string into (start_datetime, end_datetime) UTC bounds.
        """
        try:
            parts = billing_month.strip().split("-")
            if len(parts) != 2:
                raise ValueError
            year, month = int(parts[0]), int(parts[1])
            if month < 1 or month > 12:
                raise ValueError
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid billing_month format: '{billing_month}'. Expected 'YYYY-MM' (e.g. '2026-08')."
            )

        start_date = datetime(year, month, 1, 0, 0, 0)
        if month == 12:
            end_date = datetime(year + 1, 1, 1, 0, 0, 0)
        else:
            end_date = datetime(year, month + 1, 1, 0, 0, 0)
        return start_date, end_date

    def _resolve_billing_email(self, organization_name: str, org_id: Optional[str] = None) -> Optional[str]:
        """
        Resolves the appropriate recipient billing email:
        1. OrganizationWallet.payg_billing_email
        2. Primary Org Admin user email
        """
        # 1. Check wallet configured billing email
        wallet = self.session.query(OrganizationWallet).filter(
            (func.lower(OrganizationWallet.organization_name) == organization_name.lower()) |
            (OrganizationWallet.id == org_id)
        ).first()
        if wallet and wallet.payg_billing_email:
            return wallet.payg_billing_email.strip()

        # 2. Check Org Admin via RBAC role mapping
        admin_role_user = self.session.query(User).join(
            UserOrganizationRole, User.id == UserOrganizationRole.user_id
        ).join(
            OrganizationRole, UserOrganizationRole.role_id == OrganizationRole.id
        ).filter(
            func.lower(UserOrganizationRole.organization_name) == organization_name.lower(),
            OrganizationRole.name.in_(["ORG_ADMIN", "Admin", "admin"])
        ).first()
        if admin_role_user and admin_role_user.email:
            return admin_role_user.email.strip()

        # 3. Fallback: native is_org_admin user
        legacy_admin = self.session.query(User).filter(
            func.lower(User.organization_name) == organization_name.lower(),
            User.is_org_admin == True
        ).first()
        if legacy_admin and legacy_admin.email:
            return legacy_admin.email.strip()

        return None

    def generate_invoice(
        self,
        organization_name: str,
        billing_month: str,
        force_regenerate: bool = False,
        recipient_email: Optional[str] = None,
        send_email: bool = True
    ) -> PAYGInvoice:
        """
        Generates an auditable, reproducible PAYG invoice for a given organization and billing month.
        """
        org_id, org = self.tenant_resolver.resolve(organization_name)
        canonical_name = org.name
        start_date, end_date = self._parse_billing_month(billing_month)

        # 1. Duplicate check
        existing_invoice = self.session.query(PAYGInvoice).filter(
            func.lower(PAYGInvoice.organization_name) == canonical_name.lower(),
            PAYGInvoice.billing_month == billing_month
        ).first()

        if existing_invoice and not force_regenerate:
            logger.info(
                f"PAYG invoice already exists for org '{canonical_name}' in period '{billing_month}'. Returning existing ID #{existing_invoice.id}."
            )
            return existing_invoice

        # 2. Fetch all immutable AIUsageLog records for this organization within the date window
        logs = self.session.query(AIUsageLog).filter(
            (func.lower(AIUsageLog.organization_name) == canonical_name.lower()) |
            (AIUsageLog.organization_id == org_id),
            AIUsageLog.created_at >= start_date,
            AIUsageLog.created_at < end_date
        ).all()

        # 3. Group by model and aggregate input/output tokens and cost
        model_groups: Dict[str, Dict[str, Any]] = {}
        for log in logs:
            m = log.model or "unknown"
            if m not in model_groups:
                # Active rate snapshot from pricing service
                rate = float(self.pricing_service.get_price(m))
                model_groups[m] = {
                    "model": m,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "rate_per_token": rate,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "total_cost": 0.0
                }
            prompt_t = int(log.prompt_tokens or 0)
            completion_t = int(log.completion_tokens or 0)
            total_t = prompt_t + completion_t
            
            model_groups[m]["prompt_tokens"] += prompt_t
            model_groups[m]["completion_tokens"] += completion_t
            model_groups[m]["total_tokens"] += total_t
            
            # If log had recorded cost, use it; otherwise compute from rate
            log_cost = float(log.cost) if log.cost is not None and log.cost > 0 else (total_t * model_groups[m]["rate_per_token"])
            model_groups[m]["total_cost"] += log_cost

        line_items = []
        tot_prompt_tokens = 0
        tot_completion_tokens = 0
        tot_tokens = 0
        tot_input_cost = 0.0
        tot_output_cost = 0.0
        tot_cost = 0.0

        for m, item in model_groups.items():
            t_tokens = item["total_tokens"]
            p_tokens = item["prompt_tokens"]
            c_tokens = item["completion_tokens"]
            m_cost = item["total_cost"]
            rate = item["rate_per_token"]

            if t_tokens > 0:
                p_cost = round((p_tokens / t_tokens) * m_cost, 8)
                c_cost = round((c_tokens / t_tokens) * m_cost, 8)
            else:
                p_cost = 0.0
                c_cost = 0.0

            item["input_cost"] = p_cost
            item["output_cost"] = c_cost
            item["total_cost"] = round(m_cost, 8)
            line_items.append(item)

            tot_prompt_tokens += p_tokens
            tot_completion_tokens += c_tokens
            tot_tokens += t_tokens
            tot_input_cost += p_cost
            tot_output_cost += c_cost
            tot_cost += m_cost

        # 4. Resolve recipient email
        target_email = recipient_email or self._resolve_billing_email(canonical_name, org_id)

        # 5. Persist or Update Invoice Record
        if existing_invoice and force_regenerate:
            invoice = existing_invoice
            invoice.organization_id = org_id
            invoice.total_tokens = tot_tokens
            invoice.prompt_tokens = tot_prompt_tokens
            invoice.completion_tokens = tot_completion_tokens
            invoice.input_cost = Decimal(str(round(tot_input_cost, 8)))
            invoice.output_cost = Decimal(str(round(tot_output_cost, 8)))
            invoice.total_cost = Decimal(str(round(tot_cost, 8)))
            invoice.line_items = json.dumps(line_items)
            invoice.recipient_email = target_email
            invoice.generated_at = datetime.utcnow()
        else:
            invoice = PAYGInvoice(
                organization_name=canonical_name,
                organization_id=org_id,
                billing_month=billing_month,
                total_tokens=tot_tokens,
                prompt_tokens=tot_prompt_tokens,
                completion_tokens=tot_completion_tokens,
                input_cost=Decimal(str(round(tot_input_cost, 8))),
                output_cost=Decimal(str(round(tot_output_cost, 8))),
                total_cost=Decimal(str(round(tot_cost, 8))),
                line_items=json.dumps(line_items),
                invoice_status=InvoiceStatus.PENDING.value,
                recipient_email=target_email,
                generated_at=datetime.utcnow()
            )
            self.session.add(invoice)

        self.session.commit()
        self.session.refresh(invoice)

        # 6. Send billing invoice email if enabled
        if send_email and target_email:
            self.send_invoice_email(invoice, recipient_email=target_email)

        return invoice

    def generate_all_monthly_invoices(self, billing_month: Optional[str] = None) -> List[PAYGInvoice]:
        """
        Runs monthly invoice generation across all PAYG-enabled organizations.
        Defaults to previous calendar month if billing_month is not specified.
        """
        if not billing_month:
            now = datetime.utcnow()
            if now.month == 1:
                billing_month = f"{now.year - 1}-12"
            else:
                billing_month = f"{now.year}-{now.month - 1:02d}"

        # Fetch all PAYG-enabled organizations
        wallets = self.session.query(OrganizationWallet).filter(
            OrganizationWallet.payg_enabled == True
        ).all()

        invoices = []
        for w in wallets:
            try:
                inv = self.generate_invoice(
                    organization_name=w.organization_name,
                    billing_month=billing_month,
                    force_regenerate=False
                )
                invoices.append(inv)
            except Exception as e:
                logger.error(
                    f"Failed to generate PAYG invoice for org '{w.organization_name}' month '{billing_month}': {e}"
                )

        return invoices

    def send_invoice_email(self, invoice: PAYGInvoice, recipient_email: Optional[str] = None) -> bool:
        """
        Dispatches an itemized PAYG invoice email to the designated billing address.
        """
        to_email = recipient_email or invoice.recipient_email
        if not to_email:
            logger.warning(f"No recipient email found for PAYG invoice #{invoice.id} ({invoice.organization_name}).")
            return False

        line_items_data = []
        if invoice.line_items:
            try:
                line_items_data = json.loads(invoice.line_items)
            except Exception:
                pass

        subject = f"[DSuite] PAYG Invoice for {invoice.organization_name} — {invoice.billing_month}"
        
        # Build text & HTML body
        text_body = (
            f"Dear Team,\n\n"
            f"Please find your PAYG billing invoice for {invoice.organization_name} for the period {invoice.billing_month}.\n\n"
            f"Summary:\n"
            f"  - Input Tokens: {invoice.prompt_tokens:,}\n"
            f"  - Output Tokens: {invoice.completion_tokens:,}\n"
            f"  - Total Tokens: {invoice.total_tokens:,}\n"
            f"  - Input Cost: ${float(invoice.input_cost):.4f}\n"
            f"  - Output Cost: ${float(invoice.output_cost):.4f}\n"
            f"  - Total Amount Due: ${float(invoice.total_cost):.4f}\n\n"
            f"Status: {invoice.invoice_status}\n"
            f"Invoice Reference: #{invoice.id}\n\n"
            f"Thank you for choosing DSuite."
        )

        html_table_rows = "".join([
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #334155;'>{item.get('model', 'default')}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #334155;text-align:right;'>{item.get('prompt_tokens', 0):,}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #334155;text-align:right;'>{item.get('completion_tokens', 0):,}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #334155;text-align:right;'>${item.get('rate_per_token', 0):.6f}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #334155;text-align:right;font-weight:bold;'>${item.get('total_cost', 0):.4f}</td>"
            f"</tr>"
            for item in line_items_data
        ])

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>{subject}</title></head>
        <body style="font-family:Arial,sans-serif;background-color:#0f172a;color:#f8fafc;padding:24px;">
            <div style="max-width:650px;margin:0 auto;background-color:#1e293b;border-radius:12px;padding:32px;border:1px solid #334155;">
                <h2 style="color:#38bdf8;margin-top:0;">DSuite — Pay-As-You-Go Monthly Invoice</h2>
                <p><strong>Organization:</strong> {invoice.organization_name}</p>
                <p><strong>Billing Period:</strong> {invoice.billing_month}</p>
                <p><strong>Invoice ID:</strong> #{invoice.id}</p>
                
                <table style="width:100%;border-collapse:collapse;margin:20px 0;background-color:#0f172a;border-radius:8px;overflow:hidden;">
                    <thead>
                        <tr style="background-color:#334155;color:#94a3b8;font-size:13px;text-align:left;">
                            <th style="padding:10px 12px;">Model</th>
                            <th style="padding:10px 12px;text-align:right;">Input Tokens</th>
                            <th style="padding:10px 12px;text-align:right;">Output Tokens</th>
                            <th style="padding:10px 12px;text-align:right;">Rate / Token</th>
                            <th style="padding:10px 12px;text-align:right;">Amount (USD)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {html_table_rows or "<tr><td colspan='5' style='padding:12px;text-align:center;'>No usage recorded for this period.</td></tr>"}
                    </tbody>
                </table>

                <div style="background-color:#0f172a;padding:16px;border-radius:8px;margin-top:16px;">
                    <table style="width:100%;font-size:15px;">
                        <tr><td>Total Input Tokens:</td><td style="text-align:right;"><strong>{invoice.prompt_tokens:,}</strong></td></tr>
                        <tr><td>Total Output Tokens:</td><td style="text-align:right;"><strong>{invoice.completion_tokens:,}</strong></td></tr>
                        <tr><td>Total Tokens:</td><td style="text-align:right;"><strong>{invoice.total_tokens:,}</strong></td></tr>
                        <tr style="border-top:1px solid #334155;"><td style="padding-top:8px;color:#38bdf8;font-size:18px;"><strong>Total Amount Due:</strong></td><td style="padding-top:8px;text-align:right;color:#38bdf8;font-size:18px;"><strong>${float(invoice.total_cost):.4f} USD</strong></td></tr>
                    </table>
                </div>

                <p style="margin-top:24px;font-size:12px;color:#64748b;text-align:center;">
                    Generated by DSuite TokenOps. For inquiries, please contact your platform administrator.
                </p>
            </div>
        </body>
        </html>
        """

        try:
            email_service.ensure_email_delivery_configured()
            msg = email_service.EmailMessage()
            msg["Subject"] = subject
            msg["From"] = email_service._from_header()
            msg["To"] = to_email
            msg.set_content(text_body)
            msg.add_alternative(html_body, subtype="html")
            email_service._send_email_message(msg)
            logger.info(f"Delivered PAYG invoice #{invoice.id} to {to_email}")
            return True
        except Exception as e:
            logger.warning(f"Could not send email for PAYG invoice #{invoice.id}: {e}")
            return False

    def get_invoices(
        self,
        organization_name: Optional[str] = None,
        billing_month: Optional[str] = None,
        page: int = 1,
        size: int = 50
    ) -> Tuple[List[PAYGInvoice], int]:
        """
        Queries paginated list of generated invoices.
        """
        query = self.session.query(PAYGInvoice)
        if organization_name:
            query = query.filter(func.lower(PAYGInvoice.organization_name) == organization_name.lower())
        if billing_month:
            query = query.filter(PAYGInvoice.billing_month == billing_month)

        total = query.count()
        items = query.order_by(PAYGInvoice.generated_at.desc()).offset((page - 1) * size).limit(size).all()
        return items, total

    def get_invoice(self, invoice_id: int) -> Optional[PAYGInvoice]:
        return self.session.query(PAYGInvoice).filter(PAYGInvoice.id == invoice_id).first()

    def mark_invoice_paid(self, invoice_id: int) -> PAYGInvoice:
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        invoice.invoice_status = InvoiceStatus.PAID.value
        invoice.paid_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(invoice)
        return invoice
