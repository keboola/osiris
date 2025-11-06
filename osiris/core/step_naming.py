"""Step naming utilities for SQL-safe identifiers."""

import hashlib
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
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", step_id)

    # Prefix with underscore if starts with digit
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    # Warn if changed
    if sanitized != original:
        logger.warning(f"Step ID '{original}' sanitized to '{sanitized}' for SQL table name")

    return sanitized


def build_dataframe_keys(step_ids: list[str]) -> dict[str, str]:
    """Build safe DataFrame keys for multiple step IDs, detecting collisions.

    This function sanitizes step IDs and detects when multiple steps would
    produce the same sanitized name (collision). When collisions are detected,
    it appends a hash suffix to ensure uniqueness while maintaining readability.

    Args:
        step_ids: List of upstream step IDs

    Returns:
        Dictionary mapping original step_id to safe key name (e.g., "df_extract_movies")

    Raises:
        ValueError: If collision detected without hash suffix available

    Examples:
        >>> build_dataframe_keys(["extract-movies", "extract_movies"])
        {'extract-movies': 'df_extract_movies_a1b2c3d4', 'extract_movies': 'df_extract_movies_e5f6g7h8'}

        >>> build_dataframe_keys(["extract-movies"])
        {'extract-movies': 'df_extract_movies'}
    """
    if not step_ids:
        return {}

    # First pass: sanitize all IDs
    sanitized_map: dict[str, str] = {}
    for step_id in step_ids:
        sanitized_map[step_id] = sanitize_step_id(step_id)

    # Second pass: detect collisions
    sanitized_to_originals: dict[str, list[str]] = {}
    for original, sanitized in sanitized_map.items():
        if sanitized not in sanitized_to_originals:
            sanitized_to_originals[sanitized] = []
        sanitized_to_originals[sanitized].append(original)

    # Third pass: build final keys with collision detection
    result: dict[str, str] = {}
    logged_collisions: set = set()

    # First, build all result keys without logging
    for original, sanitized in sanitized_map.items():
        colliding_originals = sanitized_to_originals[sanitized]

        if len(colliding_originals) == 1:
            # No collision - use sanitized name as-is
            result[original] = f"df_{sanitized}"
        else:
            # Collision detected - append hash of original ID
            # Use first 8 chars of SHA256 hash for uniqueness + readability
            hash_suffix = hashlib.sha256(original.encode()).hexdigest()[:8]
            key = f"df_{sanitized}_{hash_suffix}"
            result[original] = key

    # Then, log collisions after all keys are built (avoids KeyError on result[o] access)
    for sanitized, colliding_originals in sanitized_to_originals.items():
        if len(colliding_originals) > 1:
            # Use tuple to ensure we only log each collision once
            collision_key = tuple(sorted(colliding_originals))
            if collision_key not in logged_collisions:
                logger.warning(
                    f"Step ID collision detected: {colliding_originals} all sanitize to '{sanitized}'. "
                    f"Using unique keys: {', '.join(f'{o}→{result[o]}' for o in colliding_originals)}"
                )
                logged_collisions.add(collision_key)

    return result
