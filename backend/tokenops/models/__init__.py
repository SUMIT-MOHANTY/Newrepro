"""
TokenOps models package.

Imports all ORM classes and enums so that callers only need:

    from tokenops.models import (
        OrganizationWallet,
        UserOrganization,
        UserTokenWallet,
        ModelPricing,
        PAYGRequest, PAYGStatus,
        PAYGInvoice, InvoiceStatus,
        TokenTransactionLedger, TransactionType, DEBIT_TYPES, CREDIT_TYPES,
        OrganizationUsageSummary,
        DEFAULT_PRICE_PER_TOKEN,
    )

All models are registered against the shared `database.Base` metadata so that
`Base.metadata.create_all(engine)` picks them up automatically when this
package is imported before the call.
"""

from tokenops.models.token_wallet import (
    OrganizationWallet,
    UserOrganization,
    UserTokenWallet,
)
from tokenops.models.pricing import (
    ModelPricing,
    DEFAULT_PRICE_PER_TOKEN,
)
from tokenops.models.payg import (
    PAYGRequest,
    PAYGStatus,
    PAYGInvoice,
    InvoiceStatus,
)
from tokenops.models.ledger import (
    TokenTransactionLedger,
    TransactionType,
    DEBIT_TYPES,
    CREDIT_TYPES,
)
from tokenops.models.summary import OrganizationUsageSummary, UserUsageSummary
from tokenops.models.idempotency import IdempotencyKey
from tokenops.models.audit import AdminAuditLog

__all__ = [
    # Wallet
    "OrganizationWallet",
    "UserOrganization",
    "UserTokenWallet",
    # Pricing
    "ModelPricing",
    "DEFAULT_PRICE_PER_TOKEN",
    # PAYG
    "PAYGRequest",
    "PAYGStatus",
    "PAYGInvoice",
    "InvoiceStatus",
    # Ledger
    "TokenTransactionLedger",
    "TransactionType",
    "DEBIT_TYPES",
    "CREDIT_TYPES",
    # Summary
    "OrganizationUsageSummary",
    "UserUsageSummary",
    # Idempotency
    "IdempotencyKey",
    # Audit
    "AdminAuditLog",
]
