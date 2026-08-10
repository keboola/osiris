"""Run identity."""

from datetime import UTC, datetime
import secrets


def new_run_id(now: datetime | None = None) -> str:
    """Sortable run id: run_<UTC compact ISO>_<6 hex>."""
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{secrets.token_hex(3)}"
