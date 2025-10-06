"""Test harness for automated validation scenario testing.

Provides functionality to run end-to-end validation scenarios for M1b.3.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from osiris.core.pipeline_validator import PipelineValidator
from osiris.core.session_logging import SessionContext
from osiris.core.validation_retry import ValidationRetryManager

logger = logging.getLogger(__name__)


def get_osiris_root() -> Path:
    """Get the Osiris project root directory."""
    # Get the path to this module
    module_path = Path(__file__).resolve()
    # Navigate up to the project root (osiris_pipeline)
    # From osiris/core/test_harness.py -> osiris_pipeline
    return module_path.parent.parent.parent


class ValidationTestHarness:
    """Automated test harness for validation scenarios."""

    def __init__(
        self,
        scenarios_dir: Path | None = None,
        max_attempts: int | None = None,
    ):
        """Initialize test harness.

        Args:
            scenarios_dir: Directory containing test scenarios (relative to project root)
            max_attempts: Override max retry attempts (uses config default if None)
        """
        # Get absolute path to scenarios based on Osiris root
        osiris_root = get_osiris_root()
        if scenarios_dir is None:
            self.scenarios_dir = osiris_root / "tests" / "scenarios"
        elif not scenarios_dir.is_absolute():
            self.scenarios_dir = osiris_root / scenarios_dir
        else:
            self.scenarios_dir = scenarios_dir
        self.console = Console()
        # max_attempts is the total number of attempts (initial + retries)
        # Default is 3 (1 initial + 2 retries)
        self.max_attempts = max_attempts if max_attempts is not None else 3

        # Initialize validator (retry manager created per scenario)
        self.validator = PipelineValidator()

        # Scenario definitions
        self.scenarios = {
            "valid": {
                "description": "Pipeline that passes validation on first attempt",
                "pipeline_file": "pipeline.yaml",
                "expected_status": "success",
                "expected_attempts": 1,
            },
            "broken": {
                "description": "Pipeline with fixable errors corrected after retry",
                "pipeline_file": "pipeline.yaml",
                "fixed_file": "pipeline_fixed.yaml",
                "expected_status": "success",
                "expected_attempts": 2,
            },
            "unfixable": {
                "description": "Pipeline that fails after max attempts",
                "pipeline_file": "pipeline.yaml",
                "expected_status": "failed",
                "expected_attempts": 3,  # 1 initial + 2 retries
            },
        }

    def run_scenario(self, scenario_name: str, output_dir: Path | None = None) -> tuple[bool, dict[str, Any]]:
        """Run a validation test scenario.

        Args:
            scenario_name: Name of scenario to run
            output_dir: Override output directory

        Returns:
            Tuple of (success, result_data)
        """
        if scenario_name not in self.scenarios:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        scenario = self.scenarios[scenario_name]
        scenario_dir = self.scenarios_dir / scenario_name

        # Set up output directory
        if output_dir is None:
            # Default to current directory with timestamped name if not specified
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path.cwd() / f"test_validation_{scenario_name}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        self.console.print(f"\n[bold cyan]Running scenario: {scenario_name}[/bold cyan]")
        self.console.print(f"[dim]{scenario['description']}[/dim]\n")

        # Create session for this test scenario
        session_id = f"test_validation_{scenario_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_ctx = SessionContext(
            session_id=session_id,
            allowed_events=["*"],  # Log all events for tests
        )

        # Log test scenario start
        session_ctx.log_event(
            "test_scenario_start",
            scenario=scenario_name,
            description=scenario["description"],
        )

        # Load pipeline
        pipeline_path = scenario_dir / scenario["pipeline_file"]
        with open(pipeline_path) as f:
            pipeline_yaml = f.read()

        # Create retry callback for broken scenario
        retry_callback = None
        if scenario_name == "broken" and "fixed_file" in scenario:
            fixed_path = scenario_dir / scenario["fixed_file"]
            with open(fixed_path) as f:
                fixed_yaml = f.read()

            def retry_callback(current_yaml, error_context, attempt):  # noqa: ARG001
                # Simulate LLM fixing the pipeline
                return fixed_yaml, {"total_tokens": 150}

        elif scenario_name == "unfixable":
            # Callback that returns same broken pipeline
            def retry_callback(current_yaml, error_context, attempt):  # noqa: ARG001
                return current_yaml, {"total_tokens": 100}

        # Create a new retry manager for this scenario
        # Note: max_attempts in ValidationRetryManager means number of RETRIES
        # So for total attempts, we need to subtract 1 (initial attempt is not a retry)
        retry_attempts = max(0, self.max_attempts - 1) if self.max_attempts is not None else 2
        retry_manager = ValidationRetryManager(
            validator=self.validator,
            max_attempts=retry_attempts,
        )

        # Run validation with retry
        success, result, retry_trail = retry_manager.validate_with_retry(
            pipeline_yaml=pipeline_yaml,
            retry_callback=retry_callback,
            session_ctx=session_ctx,
        )

        # Determine return code
        # For unfixable scenario: expected to fail, so return 1 to indicate failure
        # For other scenarios: return 0 if success, 1 if failed
        return_code = 1 if scenario_name == "unfixable" else (0 if success else 1)

        # Create result data
        result_data = {
            "scenario": scenario_name,
            "status": "success" if success else "failed",
            "attempts": len(retry_trail.attempts),
            "total_tokens": retry_trail.total_tokens,
            "total_duration_ms": retry_trail.total_duration_ms,
            "return_code": return_code,
            "errors": [],
            "retry_history": retry_trail.to_dict(),
        }

        # Add error details if failed
        if not success and retry_trail.attempts:
            last_attempt = retry_trail.attempts[-1]
            result_data["errors"] = [
                {
                    "component": e.component_type,
                    "field": e.field_path,
                    "type": e.error_type,
                    "message": e.friendly_message,
                }
                for e in last_attempt.validation_result.errors
            ]

        # Save result.json
        result_path = output_dir / "result.json"
        with open(result_path, "w") as f:
            json.dump(result_data, f, indent=2)

        # Save retry trail artifacts
        if retry_trail.attempts:
            retry_trail_path = output_dir / "retry_trail.json"
            with open(retry_trail_path, "w") as f:
                json.dump(retry_trail.to_dict(), f, indent=2)

            # Create artifacts directory for attempts
            artifacts_dir = output_dir / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)

            # Save individual attempt artifacts
            for i, attempt in enumerate(retry_trail.attempts):
                attempt_dir = artifacts_dir / f"attempt_{i + 1}"
                attempt_dir.mkdir(exist_ok=True)

                # Save pipeline YAML
                pipeline_path = attempt_dir / "pipeline.yaml"
                with open(pipeline_path, "w") as f:
                    f.write(attempt.pipeline_yaml)

                # Save errors if any
                if not attempt.validation_result.valid:
                    errors_path = attempt_dir / "errors.json"
                    errors_data = [
                        {
                            "component": e.component_type,
                            "field": e.field_path,
                            "type": e.error_type,
                            "message": e.friendly_message,
                        }
                        for e in attempt.validation_result.errors
                    ]
                    with open(errors_path, "w") as f:
                        json.dump(errors_data, f, indent=2)

        # Log scenario completion
        session_ctx.log_event(
            "test_scenario_complete",
            scenario=scenario_name,
            status=result_data["status"],
            attempts=result_data["attempts"],
            total_tokens=result_data["total_tokens"],
            duration_ms=result_data["total_duration_ms"],
        )

        # Log final metrics
        session_ctx.log_metric("attempts", result_data["attempts"])
        session_ctx.log_metric("total_tokens", result_data["total_tokens"])
        session_ctx.log_metric("total_duration_ms", result_data["total_duration_ms"])

        # Display summary table
        self._display_summary_table(retry_trail)

        # Verify expectations
        expected_status = scenario["expected_status"]
        expected_attempts = scenario["expected_attempts"]

        status_match = result_data["status"] == expected_status
        attempts_match = result_data["attempts"] == expected_attempts

        if status_match and attempts_match:
            self.console.print("\n[bold green]✓ Scenario passed expectations[/bold green]")
            self.console.print(f"  Status: {result_data['status']} (expected: {expected_status})")
            self.console.print(f"  Attempts: {result_data['attempts']} (expected: {expected_attempts})")
        else:
            self.console.print("\n[bold red]✗ Scenario failed expectations[/bold red]")
            if not status_match:
                self.console.print(f"  [red]Status mismatch:[/red] {result_data['status']} != {expected_status}")
            if not attempts_match:
                self.console.print(f"  [red]Attempts mismatch:[/red] {result_data['attempts']} != {expected_attempts}")

        self.console.print(f"\nArtifacts saved to: [cyan]{output_dir}[/cyan]")

        # Close session properly
        session_ctx.close()

        # Return success based on expectations and the return code
        return status_match and attempts_match, result_data

    def _display_summary_table(self, retry_trail):
        """Display summary table of retry attempts."""
        table = Table(title="Validation Attempts", show_header=True, header_style="bold magenta")
        table.add_column("Attempt", style="cyan", width=8)
        table.add_column("Status", width=10)
        table.add_column("Errors", justify="right", width=8)
        table.add_column("Categories", width=25)
        table.add_column("Tokens", justify="right", width=8)
        table.add_column("Duration", justify="right", width=10)

        for i, attempt in enumerate(retry_trail.attempts):
            status = "✓ Valid" if attempt.validation_result.valid else "✗ Failed"
            status_style = "green" if attempt.validation_result.valid else "red"

            error_count = len(attempt.validation_result.errors)
            categories = set()
            if error_count > 0:
                categories = {e.error_type for e in attempt.validation_result.errors}
                categories_str = ", ".join(sorted(categories)[:3])
                if len(categories) > 3:
                    categories_str += f" +{len(categories) - 3}"
            else:
                categories_str = "-"

            tokens = sum(attempt.token_usage.values()) if attempt.token_usage else 0
            duration = f"{attempt.duration_ms}ms"

            table.add_row(
                str(i + 1),
                f"[{status_style}]{status}[/{status_style}]",
                str(error_count) if error_count > 0 else "-",
                categories_str,
                str(tokens) if tokens > 0 else "-",
                duration,
            )

        # Add summary row
        table.add_section()
        table.add_row(
            "Total",
            f"[bold]{retry_trail.final_status.title()}[/bold]",
            "-",
            "-",
            str(retry_trail.total_tokens) if retry_trail.total_tokens > 0 else "-",
            f"{retry_trail.total_duration_ms}ms",
        )

        self.console.print(table)

    def run_all_scenarios(self, output_dir: Path | None = None) -> dict[str, tuple[bool, dict]]:
        """Run all validation scenarios.

        Args:
            output_dir: Base output directory for all scenarios

        Returns:
            Dictionary mapping scenario names to (success, result) tuples
        """
        results = {}

        for scenario_name in self.scenarios:
            scenario_output = output_dir / scenario_name if output_dir else None

            success, result = self.run_scenario(scenario_name, scenario_output)
            results[scenario_name] = (success, result)

        # Display overall summary
        self.console.print("\n[bold cyan]Overall Results:[/bold cyan]")
        all_passed = all(success for success, _ in results.values())

        for scenario_name, (success, result) in results.items():
            status_icon = "✓" if success else "✗"
            status_color = "green" if success else "red"
            self.console.print(
                f"  [{status_color}]{status_icon}[/{status_color}] {scenario_name}: "
                f"{result['status']} in {result['attempts']} attempts"
            )

        if all_passed:
            self.console.print("\n[bold green]All scenarios passed! 🎉[/bold green]")
        else:
            self.console.print("\n[bold red]Some scenarios failed[/bold red]")

        return results
