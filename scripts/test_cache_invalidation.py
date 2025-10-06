#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cache invalidation reproduction script for M0 validation.

This script exercises all four cache invalidation scenarios to verify
that cache behavior is working correctly with proper structured logging.

Usage:
    python scripts/test_cache_invalidation.py

Then monitor logs with:
    tail -f testing_env/osiris.log | grep -E 'event=cache_(lookup|hit|miss|store|error)'
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

# Add parent directory to Python path to import osiris modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from osiris.core.discovery import ProgressiveDiscovery


class MockExtractor:
    """Mock extractor that simulates database operations without real DB."""

    def __init__(self):
        self.call_count = 0

    async def get_table_info(self, table_name: str):
        """Mock get_table_info that returns predictable data."""
        from osiris.core.interfaces import TableInfo

        self.call_count += 1
        return TableInfo(
            name=table_name,
            columns=["id", "name", "created_at"],
            column_types={"id": "int", "name": "varchar", "created_at": "timestamp"},
            primary_keys=["id"],
            row_count=1000,
            sample_data=[
                {"id": 1, "name": "Alice", "created_at": "2024-01-01T10:00:00Z"},
                {"id": 2, "name": "Bob", "created_at": "2024-01-01T11:00:00Z"},
            ],
        )

    async def list_tables(self):
        """Mock list_tables."""
        return ["actors", "directors", "movies"]

    async def connect(self):
        """Mock connect."""
        pass

    async def disconnect(self):
        """Mock disconnect."""
        pass


class CacheTestResult:
    """Container for test scenario results."""

    def __init__(self, scenario: str, expected: str, actual: str, reason: str | None = None):
        self.scenario = scenario
        self.expected = expected
        self.actual = actual
        self.reason = reason
        self.passed = actual == expected


async def run_scenarios() -> list[CacheTestResult]:
    """Run all four cache invalidation scenarios.

    Returns:
        List of test results for each scenario
    """
    results = []

    # Use temporary cache directory for testing
    with tempfile.TemporaryDirectory(prefix="osiris-test-cache-") as cache_dir:
        print(f"Using test cache directory: {cache_dir}")
        print("Running cache invalidation scenarios...\n")

        # Basic spec schema for testing
        spec_schema = {
            "type": "object",
            "required": ["connection", "table"],
            "properties": {
                "connection": {"type": "string"},
                "table": {"type": "string"},
                "schema": {"type": "string"},
                "columns": {"type": "array"},
            },
        }

        extractor = MockExtractor()

        # Scenario 1: Cache hit on identical request
        print("1. Testing cache hit on identical request...")
        discovery1 = ProgressiveDiscovery(
            extractor=extractor,
            cache_dir=cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
            session_id="test_identical",
        )
        discovery1.set_spec_schema(spec_schema)

        req1 = {"schema": "public", "table": "actors"}

        # First call should populate cache
        await discovery1.get_table_info("actors", req1)
        calls_after_first = extractor.call_count

        # Second call should hit cache (no new extractor call)
        await discovery1.get_table_info("actors", req1)
        calls_after_second = extractor.call_count

        if calls_after_second == calls_after_first:
            results.append(CacheTestResult("identical_request", "cache_hit", "cache_hit"))
            print("✅ PASS: Cache hit on identical request")
        else:
            results.append(CacheTestResult("identical_request", "cache_hit", "cache_miss"))
            print("❌ FAIL: Expected cache hit, got cache miss")

        # Scenario 2: Options change => cache_miss
        print("2. Testing cache miss on options change...")
        discovery2 = ProgressiveDiscovery(
            extractor=extractor,
            cache_dir=cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
            session_id="test_options",
        )
        discovery2.set_spec_schema(spec_schema)

        req2_base = {"schema": "public", "table": "actors"}
        req2_changed = {"schema": "public", "table": "actors", "columns": ["actor_id", "name"]}

        await discovery2.get_table_info("actors", req2_base)
        calls_after_base = extractor.call_count

        # Changed options should miss cache
        await discovery2.get_table_info("actors", req2_changed)
        calls_after_changed = extractor.call_count

        if calls_after_changed > calls_after_base:
            results.append(CacheTestResult("options_change", "cache_miss", "cache_miss", "options_changed"))
            print("✅ PASS: Cache miss on options change")
        else:
            results.append(CacheTestResult("options_change", "cache_miss", "cache_hit"))
            print("❌ FAIL: Expected cache miss on options change, got cache hit")

        # Scenario 3: Spec change => cache_miss
        print("3. Testing cache miss on spec change...")
        discovery3 = ProgressiveDiscovery(
            extractor=extractor,
            cache_dir=cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
            session_id="test_spec",
        )
        discovery3.set_spec_schema(spec_schema)

        req3 = {"schema": "public", "table": "actors"}

        # Populate cache with original spec
        await discovery3.get_table_info("actors", req3)
        calls_after_first = extractor.call_count

        # Change spec version to simulate spec change
        discovery3.set_spec_version_override("0.1.1+test")

        # Should miss cache due to spec change
        await discovery3.get_table_info("actors", req3)
        calls_after_spec_change = extractor.call_count

        if calls_after_spec_change > calls_after_first:
            results.append(CacheTestResult("spec_change", "cache_miss", "cache_miss", "spec_changed"))
            print("✅ PASS: Cache miss on spec change")
        else:
            results.append(CacheTestResult("spec_change", "cache_miss", "cache_hit"))
            print("❌ FAIL: Expected cache miss on spec change, got cache hit")

        # Scenario 4: TTL expiry => cache_miss
        print("4. Testing cache miss on TTL expiry...")
        discovery4 = ProgressiveDiscovery(
            extractor=extractor,
            cache_dir=cache_dir,
            component_type="mysql.table",
            component_version="0.1.0",
            connection_ref="@mysql",
            session_id="test_ttl",
            ttl_seconds=2,  # Very short TTL for testing
        )
        discovery4.set_spec_schema(spec_schema)

        req4 = {"schema": "public", "table": "actors"}

        # Populate cache
        await discovery4.get_table_info("actors", req4)
        calls_after_populate = extractor.call_count

        # Wait for TTL expiry
        print("  Waiting 3 seconds for TTL expiry...")
        await asyncio.sleep(3)

        # Should miss cache due to TTL expiry
        await discovery4.get_table_info("actors", req4)
        calls_after_expiry = extractor.call_count

        if calls_after_expiry > calls_after_populate:
            results.append(CacheTestResult("ttl_expiry", "cache_miss", "cache_miss", "ttl_expired"))
            print("✅ PASS: Cache miss on TTL expiry")
        else:
            results.append(CacheTestResult("ttl_expiry", "cache_miss", "cache_hit"))
            print("❌ FAIL: Expected cache miss on TTL expiry, got cache hit")

    return results


def print_results_table(results: list[CacheTestResult]) -> None:
    """Print results in a formatted table."""
    print("\n" + "=" * 70)
    print("CACHE INVALIDATION TEST RESULTS")
    print("=" * 70)
    print(f"{'Scenario':<25} {'Result':<12} {'Reason':<20} {'Status'}")
    print("-" * 70)

    for result in results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        reason = result.reason or "N/A"
        print(f"{result.scenario:<25} {result.actual:<12} {reason:<20} {status}")

    print("-" * 70)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"SUMMARY: {passed}/{total} scenarios passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  Some tests failed. Check logs for details.")


def setup_logging():
    """Set up logging to write to testing_env/osiris.log."""
    # Create testing_env directory if it doesn't exist
    log_dir = Path("testing_env")
    log_dir.mkdir(exist_ok=True)

    # Set up file logging
    log_file = log_dir / "osiris.log"

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a"),  # Append to existing log
            logging.StreamHandler(),  # Also log to console for debugging
        ],
    )

    return log_file


def main():
    """Main entry point."""
    print("Cache Invalidation Reproduction Script")
    print("=====================================")
    print()
    print("This script tests all four cache invalidation scenarios:")
    print("1. identical_request -> cache_hit")
    print("2. options_change -> cache_miss (reason=options_changed)")
    print("3. spec_change -> cache_miss (reason=spec_changed)")
    print("4. ttl_expiry -> cache_miss (reason=ttl_expired)")
    print()

    # Set up logging to testing_env/osiris.log
    log_file = setup_logging()
    print(f"Setting up logging to: {log_file.absolute()}")
    print("Monitor structured logs with:")
    print("  tail -f testing_env/osiris.log | grep -E 'event=cache_(lookup|hit|miss|store|error)'")
    print()

    # Run the scenarios
    results = asyncio.run(run_scenarios())

    # Print results table
    print_results_table(results)

    # Print log monitoring instructions
    print("\nTo see detailed cache events, run:")
    print("  grep 'event=cache_' testing_env/osiris.log | tail -20")

    # Exit with error code if any tests failed
    failed = sum(1 for r in results if not r.passed)
    if failed > 0:
        print(f"\n❌ {failed} test(s) failed. Exiting with code 1.")
        sys.exit(1)
    else:
        print("\n✅ All tests passed. Exiting with code 0.")
        sys.exit(0)


if __name__ == "__main__":
    main()
