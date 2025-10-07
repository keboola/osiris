#!/usr/bin/env python3
"""Batch runner for ProxyWorker - reads commands.jsonl and executes them.

This script is uploaded to the E2B sandbox and executed to process
pipeline commands in batch mode with unbuffered output.
"""

import json
import os
import sys

# Ensure unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 1)
sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 1)


def main():
    """Main entry point for batch runner."""
    # Get session ID from environment or command line
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
    else:
        session_id = os.environ.get("SESSION_ID", "unknown")

    session_dir = f"/home/user/session/{session_id}"
    commands_file = f"{session_dir}/commands.jsonl"

    # Immediately signal that worker has started
    print(
        json.dumps({"type": "worker_started", "session": session_dir, "pid": os.getpid()}),
        flush=True,
    )

    # Check if commands file exists
    if not os.path.exists(commands_file):
        print(
            json.dumps({"type": "fatal", "reason": "commands_not_found", "path": commands_file}),
            flush=True,
        )
        sys.exit(2)

    # Set up Python path for imports
    sys.path.insert(0, "/home/user")

    # Import ProxyWorker
    try:
        from proxy_worker import ProxyWorker
        from rpc_protocol import parse_command
    except ImportError as e:
        print(json.dumps({"type": "fatal", "reason": "import_error", "error": str(e)}), flush=True)
        sys.exit(3)

    # Initialize worker
    print(json.dumps({"type": "worker_init", "message": "Initializing ProxyWorker"}), flush=True)

    try:
        worker = ProxyWorker()
    except Exception as e:
        print(
            json.dumps({"type": "fatal", "reason": "worker_init_failed", "error": str(e)}),
            flush=True,
        )
        sys.exit(4)

    # Process commands from file
    print(json.dumps({"type": "commands_start", "file": commands_file}), flush=True)

    command_count = 0
    with open(commands_file) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                # Parse command
                cmd_data = json.loads(line.strip())
                command_count += 1

                # Acknowledge command receipt
                print(
                    json.dumps(
                        {
                            "type": "rpc_ack",
                            "id": cmd_data.get("cmd", "unknown"),
                            "line": line_num,
                            "count": command_count,
                        }
                    ),
                    flush=True,
                )

                # Parse into command object
                command = parse_command(cmd_data)

                # Handle command
                print(
                    json.dumps({"type": "rpc_exec", "cmd": cmd_data.get("cmd", "unknown")}),
                    flush=True,
                )

                response = worker.handle_command(command)

                # Send response if any
                if response:
                    response_dict = response.model_dump(exclude_none=True)
                    response_dict["type"] = "rpc_response"
                    print(json.dumps(response_dict), flush=True)

                # Signal command completion
                print(
                    json.dumps({"type": "rpc_done", "cmd": cmd_data.get("cmd", "unknown")}),
                    flush=True,
                )

            except json.JSONDecodeError as e:
                print(
                    json.dumps(
                        {
                            "type": "error",
                            "reason": "invalid_json",
                            "line": line_num,
                            "error": str(e),
                        }
                    ),
                    flush=True,
                )

            except Exception as e:
                print(
                    json.dumps(
                        {
                            "type": "error",
                            "reason": "command_failed",
                            "line": line_num,
                            "error": str(e),
                            "cmd": (cmd_data.get("cmd", "unknown") if "cmd_data" in locals() else "parse_error"),
                        }
                    ),
                    flush=True,
                )
                # Continue processing other commands

    # Signal completion
    print(
        json.dumps({"type": "worker_complete", "commands_processed": command_count, "session": session_dir}),
        flush=True,
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(json.dumps({"type": "interrupted", "reason": "keyboard_interrupt"}), flush=True)
        sys.exit(130)
    except Exception as e:
        print(
            json.dumps({"type": "fatal", "reason": "unhandled_exception", "error": str(e)}),
            flush=True,
        )
        sys.exit(1)
