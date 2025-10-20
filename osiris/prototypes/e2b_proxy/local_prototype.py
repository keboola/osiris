#!/usr/bin/env python3
"""Local Prototype - Demonstrates JSON-RPC transparent proxy pattern without E2B."""

import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any


class LocalOrchestrator:
    """Local prototype that demonstrates the transparent proxy pattern."""

    def __init__(self):
        self.session_id = f"local_proto_{int(time.time())}"
        self.logs_dir = Path(tempfile.mkdtemp(prefix="proto_logs_"))
        self.events_file = self.logs_dir / "events.jsonl"
        self.metrics_file = self.logs_dir / "metrics.jsonl"
        self.worker_process = None
        self.output_queue = Queue()

        print(f"📁 Logs directory: {self.logs_dir}")

    def run_prototype(self):
        """Run the local prototype demonstration."""
        print("\n🚀 Starting Local Transparent Proxy Prototype\n")
        print("This demonstrates JSON-RPC communication between host and worker.\n")

        try:
            # Step 1: Start proxy worker as subprocess
            print("1️⃣ Starting ProxyWorker subprocess...")
            self.start_worker()
            print("✅ ProxyWorker started\n")

            # Give worker time to initialize
            time.sleep(0.5)

            # Step 2: Send test commands
            print("2️⃣ Sending test commands:\n")

            # Test ping/pong
            print("→ Sending PING...")
            response = self.send_command({"cmd": "ping", "data": "test-123"})
            print(f"   Response: {response}\n")

            # Test prepare
            print("→ Sending PREPARE...")
            manifest = {
                "pipeline": {"name": "test-pipeline"},
                "steps": [
                    {"id": "step-1", "type": "echo"},
                    {"id": "step-2", "type": "echo"},
                    {"id": "step-3", "type": "echo"},
                ],
            }
            response = self.send_command({"cmd": "prepare", "session_id": self.session_id, "manifest": manifest})
            print(f"   Response: {response}\n")

            # Test exec_step commands
            for step in manifest["steps"]:
                print(f"→ Sending EXEC_STEP for {step['id']}...")
                response = self.send_command(
                    {
                        "cmd": "exec_step",
                        "step_id": step["id"],
                        "config": {"type": step["type"], "test": True},
                    }
                )
                print(f"   Response: {response}\n")

            # Test cleanup
            print("→ Sending CLEANUP...")
            response = self.send_command({"cmd": "cleanup"})
            print(f"   Response: {response}\n")

            # Step 3: Show collected logs
            print("3️⃣ Collected logs:\n")
            self.display_logs()

            print("\n✅ Prototype completed successfully!")
            print("\nKey observations:")
            print("• Commands sent via stdin as JSON")
            print("• Responses received via stdout as JSON")
            print("• Events and metrics streamed separately")
            print("• Worker maintains session state")
            print("• Host writes events/metrics to log files")

            return True

        except Exception as e:
            print(f"\n❌ Prototype failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            # Cleanup
            if self.worker_process:
                print("\n🧹 Terminating worker process...")
                self.worker_process.terminate()
                self.worker_process.wait(timeout=2)

    def start_worker(self):
        """Start the proxy worker as a subprocess."""
        worker_script = Path(__file__).parent / "proxy_worker.py"

        # Start worker process
        self.worker_process = subprocess.Popen(
            [sys.executable, str(worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Start thread to read worker output
        reader_thread = threading.Thread(target=self.read_worker_output)
        reader_thread.daemon = True
        reader_thread.start()

        # Start thread to read worker stderr
        stderr_thread = threading.Thread(target=self.read_worker_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()

    def read_worker_output(self):
        """Read worker stdout in a separate thread."""
        while self.worker_process and self.worker_process.poll() is None:
            line = self.worker_process.stdout.readline()
            if line:
                try:
                    msg = json.loads(line.strip())
                    self.handle_worker_message(msg)
                except json.JSONDecodeError:
                    print(f"[Worker Raw]: {line.strip()}")

    def read_worker_stderr(self):
        """Read worker stderr in a separate thread."""
        while self.worker_process and self.worker_process.poll() is None:
            line = self.worker_process.stderr.readline()
            if line:
                print(f"[Worker Stderr]: {line.strip()}")

    def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Send a command to the worker and wait for response."""
        # Send command
        cmd_json = json.dumps(command) + "\n"
        self.worker_process.stdin.write(cmd_json)
        self.worker_process.stdin.flush()

        # Wait for response (with timeout)
        timeout = 5
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check output queue for response
            if not self.output_queue.empty():
                msg = self.output_queue.get()
                if msg.get("status"):  # This is a response
                    return msg
            time.sleep(0.01)

        return {"status": "timeout", "error": "No response from worker"}

    def handle_worker_message(self, msg: dict[str, Any]):
        """Handle a message from the worker."""
        msg_type = msg.get("type")

        if msg_type == "event":
            # Write to events log
            with open(self.events_file, "a") as f:
                f.write(json.dumps(msg) + "\n")
            print(f"   📊 Event: {msg.get('name')} - {msg.get('data', {})}")

        elif msg_type == "metric":
            # Write to metrics log
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(msg) + "\n")
            print(f"   📈 Metric: {msg.get('name')} = {msg.get('value')}")

        elif msg_type == "error":
            print(f"   ❌ Error: {msg.get('error')}")

        else:
            # This is a response, add to queue
            self.output_queue.put(msg)

    def display_logs(self):
        """Display the collected logs."""
        # Show events
        if self.events_file.exists():
            with open(self.events_file) as f:
                events = [json.loads(line) for line in f]
                print(f"📊 Events ({len(events)} total):")
                for event in events[-5:]:  # Show last 5
                    print(f"   [{event.get('name')}] {event.get('data', {})}")

        # Show metrics
        if self.metrics_file.exists():
            with open(self.metrics_file) as f:
                metrics = [json.loads(line) for line in f]
                print(f"\n📈 Metrics ({len(metrics)} total):")
                # Aggregate metrics by name
                metric_values = {}
                for metric in metrics:
                    name = metric.get("name")
                    metric_values[name] = metric.get("value")
                for name, value in metric_values.items():
                    print(f"   {name}: {value}")


if __name__ == "__main__":
    orchestrator = LocalOrchestrator()
    success = orchestrator.run_prototype()
    sys.exit(0 if success else 1)
