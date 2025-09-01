# 0001 Logging Configuration

## Status

Accepted

## Context

Logging is a critical aspect of the Osiris pipeline for monitoring, debugging, and auditing purposes. The logging configuration needs to be flexible, allowing users to specify parameters according to their environment and preferences. Key configuration parameters include:

- `logs_dir`: Directory where log files are stored.
- `level`: Logging level (e.g., DEBUG, INFO, WARNING, ERROR).
- `events`: Specific events to log; supports wildcard `*` to capture all events.

Additionally, configuration values can come from multiple sources: command-line interface (CLI), environment variables (ENV), and YAML configuration files. There must be a clear precedence order to resolve conflicts.

Session-scoped logging is required to isolate logs per pipeline run or user session.

Sensitive information such as secrets must be masked in logs to prevent leaks.

## Decision

- The logging configuration will support the parameters `logs_dir`, `level`, and `events`, with `events` supporting the wildcard character `*` to indicate all events.
- Configuration values will be resolved with the following precedence (highest to lowest):
  1. CLI arguments
  2. Environment variables
  3. YAML configuration file
  4. Default values
- Logging will be session-scoped, meaning each pipeline session will have its own isolated logging context and log files stored under the session's directory within `logs_dir`.
- Secrets and sensitive information will be automatically detected and masked in all logs to prevent exposure.
- The logging system will provide clear feedback on the effective configuration after applying precedence rules.

## Consequences

- Users can flexibly configure logging via CLI, ENV, or YAML, with predictable precedence.
- Session-scoped logs improve traceability and reduce log clutter.
- Masking secrets enhances security but requires careful implementation to avoid masking non-sensitive data.
- The wildcard support in `events` allows broad or fine-grained logging control.
- Additional complexity in configuration parsing and log management is introduced but justified by improved usability and security.
