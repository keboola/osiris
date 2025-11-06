"""Step naming utilities for SQL-safe identifiers."""

import logging
import re

logger = logging.getLogger(__name__)


def sanitize_step_id(step_id: str) -> str:
    """Sanitize step_id to be SQL-safe table name.

    Rules:
    - Replace any character that's not alphanumeric or underscore with underscore
    - If starts with digit, prefix with underscore
    - Log warning if name was changed

    Args:
        step_id: Original step identifier from OML

    Returns:
        SQL-safe identifier suitable for table names

    Examples:
        >>> sanitize_step_id("extract-movies")
        'extract_movies'
        >>> sanitize_step_id("123movies")
        '_123movies'
        >>> sanitize_step_id("extract.reviews")
        'extract_reviews'
    """
    original = step_id

    # Replace invalid characters with underscore
    sanitized = re.sub(r'[^0-9a-zA-Z_]', '_', step_id)

    # Prefix with underscore if starts with digit
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    # Warn if changed
    if sanitized != original:
        logger.warning(
            f"Step ID '{original}' sanitized to '{sanitized}' for SQL table name"
        )

    return sanitized
