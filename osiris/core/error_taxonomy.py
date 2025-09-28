"""Unified error taxonomy for Osiris pipeline execution.

This module defines standard error codes and categories that are used
consistently across local and remote execution adapters.
"""

from enum import Enum
from typing import Any


class ErrorCategory(Enum):
    """High-level error categories."""

    CONNECTION = "connection"
    EXTRACTION = "extraction"
    TRANSFORMATION = "transformation"
    WRITING = "writing"
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    RUNTIME = "runtime"
    SYSTEM = "system"


class ErrorCode(Enum):
    """Standard error codes used across all execution modes."""

    # Connection errors
    CONNECTION_FAILED = "connection.failed"
    CONNECTION_TIMEOUT = "connection.timeout"
    CONNECTION_AUTH_FAILED = "connection.auth_failed"
    CONNECTION_NOT_FOUND = "connection.not_found"
    CONNECTION_INVALID_CONFIG = "connection.invalid_config"

    # Extraction errors
    EXTRACT_QUERY_FAILED = "extract.query_failed"
    EXTRACT_NO_DATA = "extract.no_data"
    EXTRACT_SCHEMA_MISMATCH = "extract.schema_mismatch"
    EXTRACT_PERMISSION_DENIED = "extract.permission_denied"

    # Transformation errors
    TRANSFORM_FAILED = "transform.failed"
    TRANSFORM_INVALID_INPUT = "transform.invalid_input"
    TRANSFORM_TYPE_ERROR = "transform.type_error"

    # Writing errors
    WRITE_FAILED = "write.failed"
    WRITE_PERMISSION_DENIED = "write.permission_denied"
    WRITE_DISK_FULL = "write.disk_full"
    WRITE_SCHEMA_MISMATCH = "write.schema_mismatch"
    WRITE_PATH_NOT_FOUND = "write.path_not_found"

    # Validation errors
    VALIDATION_FAILED = "validation.failed"
    VALIDATION_SCHEMA_ERROR = "validation.schema_error"
    VALIDATION_CONSTRAINT_VIOLATION = "validation.constraint_violation"

    # Configuration errors
    CONFIG_INVALID = "config.invalid"
    CONFIG_MISSING_REQUIRED = "config.missing_required"
    CONFIG_TYPE_ERROR = "config.type_error"

    # Runtime errors
    RUNTIME_TIMEOUT = "runtime.timeout"
    RUNTIME_MEMORY_EXCEEDED = "runtime.memory_exceeded"
    RUNTIME_DEPENDENCY_FAILED = "runtime.dependency_failed"

    # System errors
    SYSTEM_ERROR = "system.error"
    SYSTEM_RESOURCE_UNAVAILABLE = "system.resource_unavailable"


class ErrorMapper:
    """Maps exceptions and error messages to standard error codes."""

    # Common error message patterns and their mappings
    ERROR_PATTERNS = {
        # Connection errors
        "connection refused": ErrorCode.CONNECTION_FAILED,
        "connection timeout": ErrorCode.CONNECTION_TIMEOUT,
        "authentication failed": ErrorCode.CONNECTION_AUTH_FAILED,
        "access denied": ErrorCode.CONNECTION_AUTH_FAILED,
        "password": ErrorCode.CONNECTION_AUTH_FAILED,
        "connection not found": ErrorCode.CONNECTION_NOT_FOUND,
        "invalid connection": ErrorCode.CONNECTION_INVALID_CONFIG,
        # Extraction errors
        "query failed": ErrorCode.EXTRACT_QUERY_FAILED,
        "sql error": ErrorCode.EXTRACT_QUERY_FAILED,
        "no data": ErrorCode.EXTRACT_NO_DATA,
        "empty result": ErrorCode.EXTRACT_NO_DATA,
        "schema mismatch": ErrorCode.EXTRACT_SCHEMA_MISMATCH,
        "column not found": ErrorCode.EXTRACT_SCHEMA_MISMATCH,
        "permission denied": ErrorCode.EXTRACT_PERMISSION_DENIED,
        # Write errors
        "write failed": ErrorCode.WRITE_FAILED,
        "cannot write": ErrorCode.WRITE_FAILED,
        "disk full": ErrorCode.WRITE_DISK_FULL,
        "no space left": ErrorCode.WRITE_DISK_FULL,
        "path not found": ErrorCode.WRITE_PATH_NOT_FOUND,
        "directory not found": ErrorCode.WRITE_PATH_NOT_FOUND,
        # Configuration errors
        "missing required": ErrorCode.CONFIG_MISSING_REQUIRED,
        "required field": ErrorCode.CONFIG_MISSING_REQUIRED,
        "invalid config": ErrorCode.CONFIG_INVALID,
        "type error": ErrorCode.CONFIG_TYPE_ERROR,
        # Runtime errors
        "timeout": ErrorCode.RUNTIME_TIMEOUT,
        "timed out": ErrorCode.RUNTIME_TIMEOUT,
        "memory": ErrorCode.RUNTIME_MEMORY_EXCEEDED,
        "out of memory": ErrorCode.RUNTIME_MEMORY_EXCEEDED,
    }

    @classmethod
    def map_error(cls, error_message: str, exception: Exception | None = None) -> ErrorCode:
        """Map an error message to a standard error code.

        Args:
            error_message: Error message to map
            exception: Optional exception object for additional context

        Returns:
            Standard error code
        """
        # Convert to lowercase for pattern matching
        lower_msg = error_message.lower()

        # Check patterns
        for pattern, code in cls.ERROR_PATTERNS.items():
            if pattern in lower_msg:
                return code

        # Check exception type if provided
        if exception:
            exception_name = exception.__class__.__name__.lower()

            # Database errors
            if "operational" in exception_name or "database" in exception_name:
                return ErrorCode.CONNECTION_FAILED
            elif "integrity" in exception_name:
                return ErrorCode.VALIDATION_CONSTRAINT_VIOLATION
            elif "programming" in exception_name:
                return ErrorCode.EXTRACT_QUERY_FAILED

            # I/O errors
            elif "ioerror" in exception_name or "oserror" in exception_name:
                if "permission" in str(exception).lower():
                    return ErrorCode.WRITE_PERMISSION_DENIED
                elif "no such file" in str(exception).lower():
                    return ErrorCode.WRITE_PATH_NOT_FOUND
                else:
                    return ErrorCode.WRITE_FAILED

            # Permission errors
            elif "permission" in exception_name:
                return ErrorCode.WRITE_PERMISSION_DENIED

            # File not found errors
            elif "filenotfound" in exception_name:
                return ErrorCode.WRITE_PATH_NOT_FOUND

            # Validation errors
            elif "validation" in exception_name or "schema" in exception_name:
                return ErrorCode.VALIDATION_FAILED

            # Timeout errors
            elif "timeout" in exception_name:
                return ErrorCode.RUNTIME_TIMEOUT

        # Default to system error if no match
        return ErrorCode.SYSTEM_ERROR

    @classmethod
    def format_error_event(
        cls,
        error_code: ErrorCode,
        message: str,
        step_id: str | None = None,
        source: str = "local",
        **additional_fields,
    ) -> dict[str, Any]:
        """Format an error event with standard fields.

        Args:
            error_code: Standard error code
            message: Human-readable error message
            step_id: Optional step identifier
            source: Execution source ("local" or "remote")
            **additional_fields: Additional fields to include

        Returns:
            Formatted error event dictionary
        """
        event = {
            "event": "error",
            "error_code": error_code.value,
            "category": error_code.value.split(".")[0],
            "message": message,
            "source": source,
        }

        if step_id:
            event["step_id"] = step_id

        # Add any additional fields
        event.update(additional_fields)

        return event


class ErrorContext:
    """Context for error handling and reporting."""

    def __init__(self, source: str = "local"):
        """Initialize error context.

        Args:
            source: Execution source ("local" or "remote")
        """
        self.source = source
        self.mapper = ErrorMapper()

    def handle_error(
        self,
        error_message: str,
        exception: Exception | None = None,
        step_id: str | None = None,
        **additional_fields,
    ) -> dict[str, Any]:
        """Handle an error and return formatted event.

        Args:
            error_message: Error message
            exception: Optional exception object
            step_id: Optional step identifier
            **additional_fields: Additional event fields

        Returns:
            Formatted error event
        """
        # Map to standard error code
        error_code = self.mapper.map_error(error_message, exception)

        # Format error event
        return self.mapper.format_error_event(
            error_code=error_code,
            message=error_message,
            step_id=step_id,
            source=self.source,
            **additional_fields,
        )

    def wrap_driver_error(self, driver_name: str, step_id: str, exception: Exception) -> dict[str, Any]:
        """Wrap a driver error with context.

        Args:
            driver_name: Name of the driver that failed
            step_id: Step identifier
            exception: Exception that occurred

        Returns:
            Formatted error event
        """
        error_message = str(exception)

        # Determine error category based on driver type
        if "extract" in driver_name:
            category_prefix = "extract"
        elif "write" in driver_name:
            category_prefix = "write"
        elif "transform" in driver_name:
            category_prefix = "transform"
        else:
            category_prefix = "runtime"

        # Map error with driver context
        error_code = self.mapper.map_error(error_message, exception)

        # Override with more specific code if generic or mismatched
        if error_code == ErrorCode.SYSTEM_ERROR or not error_code.value.startswith(category_prefix):
            if category_prefix == "extract":
                # For extraction, check if it's really a connection issue
                if "connect" in error_message.lower() or "connection" in error_message.lower():
                    error_code = ErrorCode.CONNECTION_FAILED
                else:
                    error_code = ErrorCode.EXTRACT_QUERY_FAILED
            elif category_prefix == "write":
                # For write, check permission errors
                if isinstance(exception, PermissionError):
                    error_code = ErrorCode.WRITE_PERMISSION_DENIED
                else:
                    error_code = ErrorCode.WRITE_FAILED
            elif category_prefix == "transform":
                error_code = ErrorCode.TRANSFORM_FAILED

        return self.mapper.format_error_event(
            error_code=error_code,
            message=error_message,
            step_id=step_id,
            source=self.source,
            driver=driver_name,
            exception_type=exception.__class__.__name__,
        )
