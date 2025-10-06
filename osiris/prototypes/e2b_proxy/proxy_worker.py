#!/usr/bin/env python3
"""ProxyWorker - Runs inside E2B sandbox and handles JSON-RPC commands."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any


class ProxyWorker:
    """Lightweight worker that processes commands from host via JSON-RPC."""

    def __init__(self):
        self.session_id = None
        self.session_dir = None
        self.step_count = 0

    def run(self):
        """Main loop - read commands from stdin, process, write responses to stdout."""
        sys.stderr.write("ProxyWorker starting...\n")
        sys.stderr.flush()

        while True:
            try:
                # Read line from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                # Parse JSON command
                cmd = json.loads(line.strip())

                # Handle command
                response = self.handle_command(cmd)

                # Send response
                if response:
                    print(json.dumps(response))
                    sys.stdout.flush()

            except json.JSONDecodeError as e:
                self.send_error(f"Invalid JSON: {e}")
            except Exception as e:
                self.send_error(f"Command failed: {e}")

    def handle_command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Process a command and return response."""
        cmd_type = cmd.get("cmd")

        if cmd_type == "prepare":
            return self.handle_prepare(cmd)
        elif cmd_type == "exec_step":
            return self.handle_exec_step(cmd)
        elif cmd_type == "cleanup":
            return self.handle_cleanup(cmd)
        elif cmd_type == "ping":
            return self.handle_ping(cmd)
        else:
            return {"status": "error", "error": f"Unknown command: {cmd_type}"}

    def handle_prepare(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Handle prepare command - initialize session."""
        self.session_id = cmd.get("session_id", "unknown")
        manifest = cmd.get("manifest", {})

        # Create session directory securely using tempfile
        # This ensures proper permissions and avoids symlink attacks
        temp_dir = tempfile.mkdtemp(prefix=f"osiris-session-{self.session_id}-")
        self.session_dir = Path(temp_dir)

        # Send event
        self.send_event("session_initialized", session_id=self.session_id)

        # Send metric
        self.send_metric("steps_total", len(manifest.get("steps", [])))

        return {
            "status": "ready",
            "session_id": self.session_id,
            "session_dir": str(self.session_dir),
        }

    def handle_exec_step(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Handle exec_step command - simulate step execution."""
        step_id = cmd.get("step_id", "unknown")
        config = cmd.get("config", {})

        # Send start event
        self.send_event("step_start", step_id=step_id)

        # Simulate work
        time.sleep(0.1)
        self.step_count += 1

        # Echo the config back (for testing)
        echo_data = {
            "step_id": step_id,
            "config_keys": list(config.keys()),
            "execution_number": self.step_count,
        }

        # Send metrics
        self.send_metric("steps_completed", self.step_count)
        self.send_metric("rows_processed", 42 * self.step_count)  # Fake metric

        # Send completion event
        self.send_event("step_complete", step_id=step_id, result=echo_data)

        return {"status": "complete", "step_id": step_id, "result": echo_data}

    def handle_cleanup(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Handle cleanup command - finalize session."""
        self.send_event("cleanup_start")

        # Clean up session directory
        if self.session_dir and self.session_dir.exists():
            # Safely remove temporary directory and all contents
            shutil.rmtree(self.session_dir, ignore_errors=True)

        self.send_event("cleanup_complete", steps_executed=self.step_count)

        return {
            "status": "cleaned",
            "session_id": self.session_id,
            "steps_executed": self.step_count,
        }

    def handle_ping(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Handle ping command - simple echo."""
        return {"status": "pong", "timestamp": time.time(), "echo": cmd.get("data", "")}

    def send_event(self, event_name: str, **kwargs):
        """Send an event to the host."""
        msg = {"type": "event", "name": event_name, "timestamp": time.time(), "data": kwargs}
        print(json.dumps(msg))
        sys.stdout.flush()

    def send_metric(self, metric_name: str, value: Any):
        """Send a metric to the host."""
        msg = {"type": "metric", "name": metric_name, "value": value, "timestamp": time.time()}
        print(json.dumps(msg))
        sys.stdout.flush()

    def send_error(self, error_msg: str):
        """Send an error to the host."""
        msg = {"type": "error", "error": error_msg, "timestamp": time.time()}
        print(json.dumps(msg))
        sys.stdout.flush()


if __name__ == "__main__":
    worker = ProxyWorker()
    worker.run()
