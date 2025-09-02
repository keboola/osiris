#!/usr/bin/env python3
"""
Manual test script for M0-Validation-4: Logging Configuration Extensions.

This script provides interactive testing of logging configuration features
that are difficult to fully automate. It demonstrates each test case from
the M0-Validation-4 document with clear output and validation.

Usage:
    python scripts/test_m0_validation_4_manual.py
"""

import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class Colors:
    """Terminal colors for output formatting."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class LoggingConfigTester:
    """Manual tester for M0-Validation-4 logging configuration."""

    def __init__(self):
        self.workspace = Path(tempfile.mkdtemp(prefix="osiris_m0_test_"))
        self.osiris_root = Path(__file__).parent.parent
        self.results = {}
        print(f"{Colors.CYAN}Test workspace: {self.workspace}{Colors.ENDC}")

    def cleanup(self):
        """Clean up test workspace."""
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def create_test_config(self, **overrides) -> Path:
        """Create a test osiris.yaml configuration."""
        config_path = self.workspace / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {
                "logs_dir": "./logs",
                "level": "INFO",
                "events": "*",
                "metrics": {"enabled": True},
                "retention": "7d",
            },
            "validate": {"mode": "warn", "json": False},
        }

        # Apply overrides
        for key, value in overrides.items():
            if "." in key:
                parts = key.split(".")
                current = config
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
            else:
                config[key] = value

        with open(config_path, "w") as f:
            yaml.dump(config, f)

        return config_path

    def run_osiris_command(self, args: list, env: Optional[Dict] = None) -> Dict[str, Any]:
        """Run an osiris command and capture output."""
        if env is None:
            env = os.environ.copy()

        # Add config path if not specified
        if "OSIRIS_CONFIG" not in env:
            config_path = self.workspace / "osiris.yaml"
            if config_path.exists():
                env["OSIRIS_CONFIG"] = str(config_path)

        # Change to workspace for relative paths
        original_cwd = os.getcwd()
        os.chdir(self.workspace)

        try:
            result = subprocess.run(  # nosec B603
                ["python", str(self.osiris_root / "osiris.py")] + args,
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Command timed out", "returncode": -1, "success": False}
        finally:
            os.chdir(original_cwd)

    def find_session_dir(self, logs_dir: Path) -> Optional[Path]:
        """Find the most recent session directory."""
        if not logs_dir.exists():
            return None

        sessions = sorted(
            [d for d in logs_dir.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        return sessions[0] if sessions else None

    def check_log_file(self, session_dir: Path, filename: str = "osiris.log") -> Dict[str, Any]:
        """Check contents of a log file."""
        log_file = session_dir / filename
        if not log_file.exists():
            return {"exists": False}

        content = log_file.read_text()
        lines = content.splitlines()

        return {
            "exists": True,
            "size": len(content),
            "lines": len(lines),
            "has_debug": any("DEBUG" in line for line in lines),
            "has_info": any("INFO" in line for line in lines),
            "has_warning": any("WARNING" in line for line in lines),
            "has_error": any("ERROR" in line for line in lines),
            "sample": lines[:5] if lines else [],
        }

    def print_test_header(self, test_name: str):
        """Print a formatted test header."""
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}{test_name}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    def print_step(self, step: str, description: str):
        """Print a test step."""
        print(f"{Colors.CYAN}Step {step}:{Colors.ENDC} {description}")

    def print_result(self, success: bool, message: str):
        """Print a test result."""
        if success:
            print(f"{Colors.GREEN}✅ PASS:{Colors.ENDC} {message}")
        else:
            print(f"{Colors.RED}❌ FAIL:{Colors.ENDC} {message}")

    def test_a_logs_dir_precedence(self):
        """Test A: logs_dir precedence and write location."""
        self.print_test_header("A) logs_dir precedence and write location")

        # Test 1: Default behavior
        self.print_step("1", "Default behavior (YAML config only)")
        self.create_test_config(**{"logging.logs_dir": "./yaml_logs"})
        result = self.run_osiris_command(["validate", "--mode", "warn"])

        yaml_logs = self.workspace / "yaml_logs"
        session = self.find_session_dir(yaml_logs)

        if session:
            self.print_result(True, f"Session created in yaml_logs: {session.name}")
        else:
            self.print_result(False, "Session not created in yaml_logs")

        # Test 2: ENV override
        self.print_step("2", "ENV override (overrides YAML)")
        env = os.environ.copy()
        env["OSIRIS_LOGS_DIR"] = "./env_logs"
        result = self.run_osiris_command(["validate", "--mode", "warn"], env=env)

        env_logs = self.workspace / "env_logs"
        session = self.find_session_dir(env_logs)

        if session:
            self.print_result(True, f"Session created in env_logs: {session.name}")
        else:
            self.print_result(False, "Session not created in env_logs")

        # Test 3: CLI override
        self.print_step("3", "CLI override (highest precedence)")
        result = self.run_osiris_command(
            ["validate", "--mode", "warn", "--logs-dir", "./cli_logs"], env=env
        )

        cli_logs = self.workspace / "cli_logs"
        session = self.find_session_dir(cli_logs)

        if session:
            self.print_result(True, f"Session created in cli_logs: {session.name}")
        else:
            self.print_result(False, "Session not created in cli_logs")

        # Test 4: Permission fallback
        self.print_step("4", "Permission fallback to temp directory")
        result = self.run_osiris_command(["validate", "--logs-dir", "/nonexistent/blocked"])

        # Check if it ran without error (fallback worked)
        if result["success"] or "permission" in result["stderr"].lower():
            self.print_result(True, "Handled permission error gracefully")
        else:
            self.print_result(False, "Did not handle permission error properly")

    def test_b_level_precedence(self):
        """Test B: level precedence and effective verbosity."""
        self.print_test_header("B) level precedence and effective verbosity")

        # Test 1: YAML level
        self.print_step("1", "YAML level (INFO)")
        self.create_test_config(**{"logging.level": "INFO"})
        self.run_osiris_command(["validate", "--mode", "warn"])

        logs_dir = self.workspace / "logs"
        session = self.find_session_dir(logs_dir)

        if session:
            log_info = self.check_log_file(session)
            if log_info["exists"] and log_info["has_info"]:
                self.print_result(True, "INFO messages present in logs")
            else:
                self.print_result(False, "INFO messages not found")

        # Test 2: ENV level override
        self.print_step("2", "ENV level override (DEBUG)")
        env = os.environ.copy()
        env["OSIRIS_LOG_LEVEL"] = "DEBUG"
        self.run_osiris_command(["validate", "--mode", "warn"], env=env)

        session = self.find_session_dir(logs_dir)
        if session:
            log_info = self.check_log_file(session)
            if log_info["exists"] and log_info["has_debug"]:
                self.print_result(True, "DEBUG messages present with ENV override")
            else:
                self.print_result(False, "DEBUG messages not found")

        # Test 3: CLI level override
        self.print_step("3", "CLI level override (ERROR)")
        self.run_osiris_command(["validate", "--log-level", "ERROR"], env=env)

        session = self.find_session_dir(logs_dir)
        if session:
            log_info = self.check_log_file(session)
            # With ERROR level, should not have INFO or DEBUG
            if log_info["exists"] and not log_info["has_info"] and not log_info["has_debug"]:
                self.print_result(True, "Only ERROR+ messages with CLI override")
            else:
                self.print_result(False, "Lower level messages still present")

    def test_c_events_metrics(self):
        """Test C: events/metrics toggles."""
        self.print_test_header("C) events/metrics toggles")

        # Test 1: Events and metrics enabled
        self.print_step("1", "Events and metrics enabled")
        self.create_test_config(**{"logging.write_events": True, "logging.write_metrics": True})
        self.run_osiris_command(["validate"])

        logs_dir = self.workspace / "logs"
        session = self.find_session_dir(logs_dir)

        if session:
            events_file = session / "events.jsonl"
            metrics_file = session / "metrics.jsonl"

            if events_file.exists():
                self.print_result(
                    True, f"events.jsonl created ({events_file.stat().st_size} bytes)"
                )
            else:
                self.print_result(False, "events.jsonl not created")

            if metrics_file.exists():
                self.print_result(
                    True, f"metrics.jsonl created ({metrics_file.stat().st_size} bytes)"
                )
            else:
                self.print_result(False, "metrics.jsonl not created")

    def test_e_secrets_redaction(self):
        """Test E: secrets redaction in logging."""
        self.print_test_header("E) secrets redaction in logging")

        # Create config with fake secrets
        config_path = self.workspace / "osiris.yaml"
        config = {
            "version": "2.0",
            "logging": {"logs_dir": "./logs", "level": "DEBUG", "events": "*"},
            "database": {
                "password": "SuperSecret123",  # pragma: allowlist secret
                "api_key": "sk-test-XYZ",  # pragma: allowlist secret
            },
        }

        with open(config_path, "w") as f:
            yaml.dump(config, f)

        self.print_step("1", "Running command that touches secrets")
        self.run_osiris_command(["validate"])

        self.print_step("2", "Scanning logs for plaintext secrets")
        logs_dir = self.workspace / "logs"
        session = self.find_session_dir(logs_dir)

        if session:
            secrets_found = []
            for file_path in session.rglob("*"):
                if file_path.is_file():
                    try:
                        content = file_path.read_text()
                        if "SuperSecret123" in content:
                            secrets_found.append(f"{file_path.name}: contains password")
                        if "sk-test-XYZ" in content:
                            secrets_found.append(f"{file_path.name}: contains API key")
                    except Exception:  # nosec B110
                        pass

            if not secrets_found:
                self.print_result(True, "No plaintext secrets found in logs")
            else:
                self.print_result(False, f"Secrets found: {', '.join(secrets_found)}")

    def test_log_level_comparison(self):
        """Special test: Compare DEBUG vs CRITICAL log outputs."""
        self.print_test_header("Log Level Comparison: DEBUG vs CRITICAL")

        self.create_test_config()

        # Run with DEBUG
        self.print_step("1", "Running with DEBUG level")
        self.run_osiris_command(["validate", "--log-level", "DEBUG", "--logs-dir", "./debug_logs"])

        debug_dir = self.workspace / "debug_logs"
        debug_session = self.find_session_dir(debug_dir)
        debug_info = None

        if debug_session:
            debug_info = self.check_log_file(debug_session)
            print(f"  DEBUG log: {debug_info['lines']} lines, {debug_info['size']} bytes")

        # Run with CRITICAL
        self.print_step("2", "Running with CRITICAL level")
        self.run_osiris_command(
            ["validate", "--log-level", "CRITICAL", "--logs-dir", "./critical_logs"]
        )

        critical_dir = self.workspace / "critical_logs"
        critical_session = self.find_session_dir(critical_dir)
        critical_info = None

        if critical_session:
            critical_info = self.check_log_file(critical_session)
            print(f"  CRITICAL log: {critical_info['lines']} lines, {critical_info['size']} bytes")

        # Compare
        self.print_step("3", "Comparing results")
        if debug_info and critical_info:
            if debug_info["size"] > critical_info["size"]:
                diff = debug_info["size"] - critical_info["size"]
                self.print_result(True, f"DEBUG logs are {diff} bytes larger than CRITICAL")
            else:
                self.print_result(False, "DEBUG logs should be larger than CRITICAL")

            if debug_info["has_debug"] and not critical_info["has_debug"]:
                self.print_result(True, "DEBUG messages only in DEBUG level")
            else:
                self.print_result(False, "DEBUG message filtering issue")

    def run_all_tests(self):
        """Run all manual tests."""
        print(
            f"\n{Colors.BOLD}{Colors.BLUE}M0-VALIDATION-4: MANUAL LOGGING CONFIGURATION TESTS{Colors.ENDC}"
        )
        print(
            f"{Colors.BLUE}Testing Osiris logging configuration features interactively{Colors.ENDC}\n"
        )

        try:
            # Run each test category
            self.test_a_logs_dir_precedence()
            self.test_b_level_precedence()
            self.test_c_events_metrics()
            self.test_e_secrets_redaction()
            self.test_log_level_comparison()

            # Summary
            print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}{Colors.GREEN}TEST SUITE COMPLETED{Colors.ENDC}")
            print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
            print(f"\n{Colors.YELLOW}Test workspace preserved at: {self.workspace}{Colors.ENDC}")
            print(f"{Colors.YELLOW}You can examine the logs manually if needed.{Colors.ENDC}")

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.RED}Test error: {e}{Colors.ENDC}")
            import traceback

            traceback.print_exc()

    def interactive_mode(self):
        """Run tests interactively with user prompts."""
        print(f"\n{Colors.BOLD}{Colors.BLUE}M0-VALIDATION-4: INTERACTIVE TEST MODE{Colors.ENDC}")
        print(f"{Colors.BLUE}This mode allows you to run tests one at a time{Colors.ENDC}\n")

        tests = [
            ("A", "logs_dir precedence", self.test_a_logs_dir_precedence),
            ("B", "level precedence", self.test_b_level_precedence),
            ("C", "events/metrics toggles", self.test_c_events_metrics),
            ("E", "secrets redaction", self.test_e_secrets_redaction),
            ("L", "log level comparison", self.test_log_level_comparison),
        ]

        while True:
            print(f"\n{Colors.CYAN}Available tests:{Colors.ENDC}")
            for key, name, _ in tests:
                print(f"  {key}) {name}")
            print("  Q) Quit")

            choice = input(f"\n{Colors.YELLOW}Select test to run: {Colors.ENDC}").strip().upper()

            if choice == "Q":
                break

            for key, _name, func in tests:
                if choice == key:
                    func()
                    input(f"\n{Colors.YELLOW}Press Enter to continue...{Colors.ENDC}")
                    break
            else:
                print(f"{Colors.RED}Invalid choice{Colors.ENDC}")


def main():
    """Main entry point."""
    tester = LoggingConfigTester()

    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
            tester.interactive_mode()
        else:
            tester.run_all_tests()

            # Ask if user wants to clean up
            response = input(f"\n{Colors.YELLOW}Clean up test workspace? (y/n): {Colors.ENDC}")
            if response.lower() == "y":
                tester.cleanup()
                print(f"{Colors.GREEN}Workspace cleaned up{Colors.ENDC}")
            else:
                print(f"{Colors.YELLOW}Workspace preserved at: {tester.workspace}{Colors.ENDC}")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Interrupted by user{Colors.ENDC}")
        tester.cleanup()
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.ENDC}")
        import traceback

        traceback.print_exc()
        tester.cleanup()


if __name__ == "__main__":
    main()
