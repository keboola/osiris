"""Retry mechanism for pipeline validation failures.

Implements bounded retry logic per ADR-0013 with HITL escalation.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import inspect
import json
import logging
from pathlib import Path
import time
from typing import Any

import yaml

from osiris.core.pipeline_validator import PipelineValidator, ValidationResult
from osiris.core.session_logging import SessionContext

logger = logging.getLogger(__name__)


@dataclass
class RetryAttempt:
    """Represents a single retry attempt."""

    attempt_number: int
    pipeline_yaml: str
    validation_result: ValidationResult
    token_usage: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Get error categories
        error_categories = []
        if not self.validation_result.valid and self.validation_result.errors:
            error_categories = list({e.error_type for e in self.validation_result.errors})

        return {
            "attempt_number": self.attempt_number,
            "valid": self.validation_result.valid,
            "error_count": (len(self.validation_result.errors) if not self.validation_result.valid else 0),
            "error_categories": error_categories,
            "duration_ms": self.duration_ms,
            "tokens": {
                "prompt": self.token_usage.get("prompt_tokens"),
                "response": self.token_usage.get("completion_tokens"),
                "total": self.token_usage.get("total_tokens", self.token_usage.get("total")),
            },
            "timestamp": self.timestamp,
            "validation_result": self.validation_result.to_dict(),
            "status": "success" if self.validation_result.valid else "failed",
        }

    def get_summary(self, max_tokens: int = 200) -> str:
        """Get a concise summary for HITL display."""
        result = self.validation_result
        if result.valid:
            return f"Attempt {self.attempt_number}: ✓ Success"

        # Summarize top errors
        errors = result.errors[:3]  # Show top 3 errors
        summary_parts = [f"Attempt {self.attempt_number}: ❌ Failed ({len(result.errors)} errors)"]

        for error in errors:
            summary_parts.append(f"  • {error.component_type}: {error.friendly_message[:50]}")

        if len(result.errors) > 3:
            summary_parts.append(f"  ... and {len(result.errors) - 3} more")

        summary = "\n".join(summary_parts)

        # Rough token estimation (4 chars per token)
        while len(summary) / 4 > max_tokens and len(summary_parts) > 2:
            summary_parts.pop()
            summary = "\n".join(summary_parts) + "..."

        return summary


@dataclass
class RetryTrail:
    """Complete retry history for HITL escalation."""

    attempts: list[RetryAttempt] = field(default_factory=list)
    total_tokens: int = 0
    total_duration_ms: int = 0
    final_status: str = "pending"

    def add_attempt(self, attempt: RetryAttempt):
        """Add a retry attempt to the trail."""
        self.attempts.append(attempt)
        self.total_tokens += sum(attempt.token_usage.values())
        self.total_duration_ms += attempt.duration_ms

        if attempt.validation_result.valid:
            self.final_status = "success"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "attempts": [a.to_dict() for a in self.attempts],
            "total_attempts": len(self.attempts),
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "final_status": self.final_status,
        }

    def get_hitl_summary(self, history_limit: int = 3) -> str:
        """Get a formatted summary for HITL display."""
        lines = ["🔄 Validation Retry History:"]

        # Show last N attempts
        shown_attempts = self.attempts[-history_limit:] if history_limit else self.attempts

        for attempt in shown_attempts:
            lines.append(attempt.get_summary())

        if len(self.attempts) > history_limit:
            lines.insert(1, f"(Showing last {history_limit} of {len(self.attempts)} attempts)")

        lines.append(f"\nTotal tokens used: {self.total_tokens}")
        lines.append(f"Total time: {self.total_duration_ms / 1000:.1f}s")

        return "\n".join(lines)

    def save_artifacts(self, session_dir: Path):
        """Save retry artifacts to session directory."""
        artifacts_dir = session_dir / "artifacts" / "retries"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Save each attempt
        for attempt in self.attempts:
            attempt_dir = artifacts_dir / f"attempt_{attempt.attempt_number}"
            attempt_dir.mkdir(parents=True, exist_ok=True)

            # Save pipeline YAML (redacted)
            pipeline_path = attempt_dir / "pipeline.yaml"
            pipeline_path.write_text(attempt.pipeline_yaml)

            # Save errors JSON
            errors_path = attempt_dir / "errors.json"
            errors_path.write_text(json.dumps(attempt.validation_result.to_dict(), indent=2))

            # Save patch if not first attempt
            if attempt.attempt_number > 1:
                prev_attempt = self.attempts[attempt.attempt_number - 2]
                patch = self._generate_patch(prev_attempt.pipeline_yaml, attempt.pipeline_yaml)
                patch_path = attempt_dir / "patch.json"
                patch_path.write_text(json.dumps(patch, indent=2))

        # Save summary
        summary_dir = artifacts_dir.parent / "summary"
        summary_dir.mkdir(parents=True, exist_ok=True)
        summary_path = summary_dir / "retry_trail.json"
        summary_path.write_text(json.dumps(self.to_dict(), indent=2))

    def _generate_patch(self, old_yaml: str, new_yaml: str) -> dict[str, Any]:
        """Generate a patch showing differences between attempts."""
        try:
            old_dict = yaml.safe_load(old_yaml) or {}
            new_dict = yaml.safe_load(new_yaml) or {}

            # Simple diff - track changes
            patch = {"changes": [], "additions": [], "deletions": []}

            # Find changes in steps
            old_steps = old_dict.get("steps", [])
            new_steps = new_dict.get("steps", [])

            for i, (old_step, new_step) in enumerate(zip(old_steps, new_steps, strict=False)):
                if old_step != new_step:
                    patch["changes"].append(
                        {
                            "step": i,
                            "field": "config",
                            "old": old_step.get("config"),
                            "new": new_step.get("config"),
                        }
                    )

            # Check for added/removed steps
            if len(new_steps) > len(old_steps):
                patch["additions"].extend(new_steps[len(old_steps) :])
            elif len(old_steps) > len(new_steps):
                patch["deletions"].extend(old_steps[len(new_steps) :])

            return patch

        except Exception as e:
            logger.error(f"Failed to generate patch: {e}")
            return {"error": str(e)}


class ValidationRetryManager:
    """Manages retry logic for pipeline validation."""

    def __init__(
        self,
        validator: PipelineValidator | None = None,
        max_attempts: int = 2,
        include_history_in_hitl: bool = True,
        history_limit: int = 3,
        diff_format: str = "patch",
    ):
        """Initialize retry manager.

        Args:
            validator: Pipeline validator instance
            max_attempts: Maximum retry attempts (0-5)
            include_history_in_hitl: Whether to show history in HITL
            history_limit: Max attempts to show in HITL history
            diff_format: Format for diffs ("patch" or "summary")
        """
        self.validator = validator or PipelineValidator()
        self.max_attempts = min(max(max_attempts, 0), 5)  # Enforce 0-5 range
        self.include_history_in_hitl = include_history_in_hitl
        self.history_limit = history_limit
        self.diff_format = diff_format
        self.retry_trail = RetryTrail()

    def validate_with_retry(
        self,
        pipeline_yaml: str,
        retry_callback: Any | None = None,
        session_ctx: SessionContext | None = None,
    ) -> tuple[bool, ValidationResult, RetryTrail]:
        """Validate pipeline with automatic retry on failure.

        Args:
            pipeline_yaml: Initial pipeline YAML
            retry_callback: Callable to generate retry with error context
            session_ctx: Session context for logging

        Returns:
            Tuple of (success, final_result, retry_trail)
        """
        current_yaml = pipeline_yaml
        attempt_num = 1

        while attempt_num <= self.max_attempts + 1:  # +1 for initial attempt
            # Log validation start
            if session_ctx:
                session_ctx.log_event("validation_attempt_start", attempt=attempt_num)

            # Validate
            start_time = time.time()
            result = self.validator.validate_pipeline(current_yaml)
            duration_ms = int((time.time() - start_time) * 1000)

            # Create attempt record
            attempt = RetryAttempt(
                attempt_number=attempt_num,
                pipeline_yaml=current_yaml,
                validation_result=result,
                duration_ms=duration_ms,
            )

            # Log validation complete
            if session_ctx:
                session_ctx.log_event(
                    "validation_attempt_complete",
                    attempt=attempt_num,
                    status="success" if result.valid else "failed",
                    error_count=len(result.errors),
                    error_categories=list({e.error_type for e in result.errors}),
                    duration_ms=duration_ms,
                )

            self.retry_trail.add_attempt(attempt)

            # Check if valid or max attempts reached
            if result.valid:
                self.retry_trail.final_status = "success"
                return True, result, self.retry_trail

            if attempt_num > self.max_attempts:
                self.retry_trail.final_status = "failed"
                break

            # Retry with error context
            if retry_callback:
                retry_prompt = self.validator.get_retry_prompt_context(result.errors)

                # Log retry event
                if session_ctx:
                    session_ctx.log_event(
                        "validation_retry",
                        attempt=attempt_num + 1,
                        previous_errors=len(result.errors),
                        retry_prompt_length=len(retry_prompt),
                    )

                # Generate retry
                try:
                    # Handle both sync and async callbacks
                    if inspect.iscoroutinefunction(retry_callback):
                        # Async callback - run with asyncio
                        try:
                            new_yaml, token_usage = asyncio.run(retry_callback(current_yaml, retry_prompt, attempt_num))
                        except RuntimeError:
                            # Already running in an event loop - this shouldn't happen in normal usage
                            logger.error("Cannot run async callback from within an existing event loop")
                            break
                    else:
                        # Synchronous callback
                        new_yaml, token_usage = retry_callback(current_yaml, retry_prompt, attempt_num)

                    current_yaml = new_yaml

                    # Update token usage
                    if token_usage:
                        attempt.token_usage = token_usage
                        self.retry_trail.total_tokens += sum(token_usage.values())

                except Exception as e:
                    logger.error(f"Retry callback failed: {e}")
                    break
            else:
                # No retry callback, can't retry
                break

            attempt_num += 1

        # All retries exhausted
        return False, result, self.retry_trail

    def get_hitl_prompt(self, retry_trail: RetryTrail | None = None) -> str:
        """Generate HITL prompt with retry history.

        Args:
            retry_trail: Retry trail to include (uses self.retry_trail if None)

        Returns:
            Formatted HITL prompt string
        """
        trail = retry_trail or self.retry_trail

        lines = ["❌ Automatic validation failed after all retry attempts.", ""]

        if self.include_history_in_hitl and trail.attempts:
            lines.append(trail.get_hitl_summary(self.history_limit))
            lines.append("")

        # Show current errors
        if trail.attempts:
            last_attempt = trail.attempts[-1]
            lines.append("Current validation errors:")
            lines.append(last_attempt.validation_result.get_friendly_summary())
            lines.append("")

        lines.append("Please provide additional information to fix these errors:")
        lines.append("(You can specify correct values, clarify requirements, or adjust the pipeline)")

        return "\n".join(lines)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ValidationRetryManager":
        """Create retry manager from configuration dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            Configured ValidationRetryManager instance
        """
        validation_config = config.get("validation", {})
        retry_config = validation_config.get("retry", {})

        return cls(
            max_attempts=retry_config.get("max_attempts", 2),
            include_history_in_hitl=retry_config.get("include_history_in_hitl", True),
            history_limit=retry_config.get("history_limit", 3),
            diff_format=retry_config.get("diff_format", "patch"),
        )
