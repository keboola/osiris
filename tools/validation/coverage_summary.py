#!/usr/bin/env python3
"""Coverage summary tool for Osiris test suite.

This script reads coverage.json and produces:
- Per-folder coverage table (markdown format)
- Per-file list of files under threshold
- Exit with non-zero if any folder falls below minimum thresholds

Usage:
    python tools/validation/coverage_summary.py [OPTIONS] coverage.json

Options:
    --remote-min FLOAT   Minimum coverage for remote/ module (default: 0.8)
    --llm-min FLOAT      Minimum coverage for llm/prompts modules (default: 0.75)
    --cli-min FLOAT      Minimum coverage for cli/ module (default: 0.7)
    --core-min FLOAT     Minimum coverage for core/ module (default: 0.7)
    --overall-min FLOAT  Minimum overall coverage (default: 0.5)
    --format FORMAT      Output format: markdown, json, or text (default: markdown)
    --output FILE        Output file (default: stdout)
    --threshold FLOAT    Show files below this threshold (default: 0.6)
"""

import argparse
import json
from pathlib import Path
import sys


class CoverageSummary:
    """Analyzes coverage.json and produces summary reports."""

    def __init__(self, coverage_file: str):
        """Initialize with coverage.json file path."""
        self.coverage_file = Path(coverage_file)
        if not self.coverage_file.exists():
            raise FileNotFoundError(f"Coverage file not found: {coverage_file}")

        with open(self.coverage_file) as f:
            self.data = json.load(f)

        self.modules = self._analyze_modules()

    def _analyze_modules(self) -> dict[str, dict]:
        """Analyze coverage by module/folder."""
        modules = {}

        for file_path, file_data in self.data["files"].items():
            if "/osiris/" not in file_path:
                continue

            # Extract module from path
            parts = file_path.split("/osiris/")[-1].split("/")
            module = parts[0] if len(parts) > 1 else "root"

            if module not in modules:
                modules[module] = {
                    "total_lines": 0,
                    "covered_lines": 0,
                    "files": [],
                    "low_coverage_files": [],
                }

            summary = file_data["summary"]
            file_lines = summary["num_statements"]
            file_covered = int(summary["covered_lines"])
            file_percent = summary["percent_covered"] / 100.0

            modules[module]["total_lines"] += file_lines
            modules[module]["covered_lines"] += file_covered
            modules[module]["files"].append(
                {
                    "path": file_path,
                    "name": file_path.split("/")[-1],
                    "coverage": file_percent,
                    "lines": file_lines,
                    "covered": file_covered,
                }
            )

        # Calculate percentages
        for module in modules.values():
            if module["total_lines"] > 0:
                module["coverage"] = module["covered_lines"] / module["total_lines"]
            else:
                module["coverage"] = 0.0

        return modules

    def get_overall_coverage(self) -> tuple[float, int, int]:
        """Get overall coverage statistics."""
        totals = self.data["totals"]
        percent = totals["percent_covered"] / 100.0
        covered = int(totals["covered_lines"])
        total = totals["num_statements"]
        return percent, covered, total

    def get_module_table(self, sort_by="coverage", ascending=True) -> list[dict]:
        """Get module coverage as sortable table."""
        table = []
        for name, stats in self.modules.items():
            table.append(
                {
                    "module": name,
                    "coverage": stats["coverage"],
                    "covered_lines": stats["covered_lines"],
                    "total_lines": stats["total_lines"],
                    "file_count": len(stats["files"]),
                }
            )

        return sorted(table, key=lambda x: x[sort_by], reverse=not ascending)

    def get_low_coverage_files(self, threshold: float = 0.6) -> list[dict]:
        """Get files below coverage threshold."""
        low_coverage = []

        for module_name, module in self.modules.items():
            for file_info in module["files"]:
                if file_info["coverage"] < threshold:
                    low_coverage.append(
                        {
                            "module": module_name,
                            "file": file_info["name"],
                            "path": file_info["path"],
                            "coverage": file_info["coverage"],
                            "lines": file_info["lines"],
                        }
                    )

        return sorted(low_coverage, key=lambda x: x["coverage"])

    def check_thresholds(self, thresholds: dict[str, float]) -> tuple[bool, list[str]]:
        """Check if modules meet minimum thresholds."""
        failures = []

        for module_name, min_coverage in thresholds.items():
            if module_name == "overall":
                actual, _, _ = self.get_overall_coverage()
                if actual < min_coverage:
                    failures.append(f"Overall coverage {actual:.1%} < {min_coverage:.1%}")
            elif module_name in self.modules:
                actual = self.modules[module_name]["coverage"]
                if actual < min_coverage:
                    failures.append(f"Module '{module_name}' coverage {actual:.1%} < {min_coverage:.1%}")

        return len(failures) == 0, failures

    def format_markdown(self, threshold: float = 0.6) -> str:
        """Format coverage summary as markdown."""
        output = []

        # Overall stats
        percent, covered, total = self.get_overall_coverage()
        output.append("# Coverage Summary\n")
        output.append(f"**Overall Coverage**: {percent:.2%} ({covered:,}/{total:,} lines)\n")
        output.append("")

        # Module table
        output.append("## Module Coverage (sorted by coverage ascending)\n")
        output.append("| Module | Coverage | Lines | Files |")
        output.append("|--------|----------|-------|-------|")

        for row in self.get_module_table():
            status = "🔴" if row["coverage"] < 0.4 else "🟡" if row["coverage"] < 0.7 else "🟢"
            output.append(
                f"| {row['module']} | {status} {row['coverage']:.1%} | "
                f"{row['covered_lines']:,}/{row['total_lines']:,} | "
                f"{row['file_count']} |"
            )

        output.append("")

        # Low coverage files
        low_files = self.get_low_coverage_files(threshold)
        if low_files:
            output.append(f"## Files Below {threshold:.0%} Coverage\n")
            output.append("| Module | File | Coverage | Lines |")
            output.append("|--------|------|----------|-------|")

            for file_info in low_files[:20]:  # Top 20
                output.append(
                    f"| {file_info['module']} | {file_info['file']} | "
                    f"{file_info['coverage']:.1%} | {file_info['lines']} |"
                )

        return "\n".join(output)

    def format_json(self) -> str:
        """Format coverage summary as JSON."""
        percent, covered, total = self.get_overall_coverage()
        return json.dumps(
            {
                "overall": {"coverage": percent, "covered_lines": covered, "total_lines": total},
                "modules": self.get_module_table(),
                "low_coverage_files": self.get_low_coverage_files(),
            },
            indent=2,
        )

    def format_text(self, threshold: float = 0.6) -> str:
        """Format coverage summary as plain text."""
        _ = threshold  # Unused but kept for API consistency
        output = []

        percent, covered, total = self.get_overall_coverage()
        output.append(f"Overall Coverage: {percent:.2%} ({covered}/{total} lines)")
        output.append("")
        output.append("Module Coverage:")

        for row in self.get_module_table():
            output.append(
                f"  {row['module']:20s} {row['coverage']:6.1%} "
                f"({row['covered_lines']}/{row['total_lines']} lines, "
                f"{row['file_count']} files)"
            )

        return "\n".join(output)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze test coverage")
    parser.add_argument("coverage_file", help="Path to coverage.json")
    parser.add_argument("--remote-min", type=float, default=0.8, help="Minimum coverage for remote/ module")
    parser.add_argument("--llm-min", type=float, default=0.75, help="Minimum coverage for llm/prompts modules")
    parser.add_argument("--cli-min", type=float, default=0.7, help="Minimum coverage for cli/ module")
    parser.add_argument("--core-min", type=float, default=0.7, help="Minimum coverage for core/ module")
    parser.add_argument("--overall-min", type=float, default=0.5, help="Minimum overall coverage")
    parser.add_argument("--format", choices=["markdown", "json", "text"], default="markdown", help="Output format")
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--threshold", type=float, default=0.6, help="Show files below this threshold")

    args = parser.parse_args()

    try:
        summary = CoverageSummary(args.coverage_file)

        # Format output
        if args.format == "markdown":
            output = summary.format_markdown(args.threshold)
        elif args.format == "json":
            output = summary.format_json()
        else:
            output = summary.format_text(args.threshold)

        # Write output
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
        else:
            print(output)

        # Check thresholds
        thresholds = {
            "overall": args.overall_min,
            "remote": args.remote_min,
            "prompts": args.llm_min,
            "cli": args.cli_min,
            "core": args.core_min,
        }

        passed, failures = summary.check_thresholds(thresholds)

        if not passed:
            print("\n⚠️  Coverage thresholds not met:", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
            sys.exit(1)
        else:
            if not args.output:  # Only print if not writing to file
                print("\n✅ All coverage thresholds met!", file=sys.stderr)
            sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
