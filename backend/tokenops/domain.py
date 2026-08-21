from dataclasses import dataclass

@dataclass
class WalletState:
    """
    Domain object representing the current state of a wallet.
    Used for transferring state between repositories and services.
    """
    allocated: int
    consumed: int
    remaining: int
    reserved: int

@dataclass
class TokenTransaction:
    """
    Domain object representing an atomic token movement.
    Used as input for the LedgerService.
    """
    organization_name: str
    transaction_type: str
    token_delta: int
    reference_id: str | None = None
    user_id: int | None = None
    remarks: str | None = None
