"""CLI commands for running automated tests."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from osiris.core.test_harness import ValidationTestHarness

logger = logging.getLogger(__name__)
console = Console()


@click.group()
def test():
    """Run automated test scenarios."""
    pass


@test.command()
@click.option(
    "--scenario",
    type=click.Choice(["valid", "broken", "unfixable", "all"], case_sensitive=False),
    default="all",
    help="Scenario to run (default: all)",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    help="Output directory for artifacts",
)
@click.option(
    "--max-attempts",
    type=int,
    help="Override max retry attempts",
)
def validation(scenario: str, out: Optional[Path], max_attempts: Optional[int]):
    """Run validation test scenarios.

    Scenarios:
    - valid: Pipeline that passes validation on first attempt
    - broken: Pipeline with fixable errors corrected after retry
    - unfixable: Pipeline that fails after max attempts
    - all: Run all scenarios
    """
    try:
        # Initialize test harness
        harness = ValidationTestHarness(max_attempts=max_attempts)

        if scenario == "all":
            # Run all scenarios
            results = harness.run_all_scenarios(output_dir=out)

            # Check if all passed
            all_passed = all(success for success, _ in results.values())
            sys.exit(0 if all_passed else 1)
        else:
            # Run single scenario
            success, result = harness.run_scenario(scenario, output_dir=out)
            sys.exit(0 if success else 1)

    except Exception as e:
        console.print(f"[bold red]Error running test scenario: {e}[/bold red]")
        logger.error(f"Test scenario failed: {e}", exc_info=True)
        sys.exit(1)
