"""E2B integration for remote pipeline execution."""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from ..core.session_logging import log_event, log_metric
from .e2b_client import E2BClient, SandboxStatus
from .e2b_pack import PayloadBuilder, RunConfig


@dataclass
class E2BConfig:
    """Configuration for E2B execution."""

    enabled: bool = False
    timeout: int = 900
    cpu: int = 2
    mem_gb: int = 4
    env_vars: Dict[str, str] = None
    dry_run: bool = False

    def __post_init__(self):
        if self.env_vars is None:
            self.env_vars = {}


def parse_e2b_args(args: List[str]) -> Tuple[E2BConfig, List[str]]:
    """Parse E2B-specific arguments from command line.

    Returns:
        Tuple of (E2BConfig, remaining_args)
    """
    config = E2BConfig()
    remaining_args = []
    i = 0

    while i < len(args):
        arg = args[i]

        if arg == "--e2b":
            config.enabled = True
        elif arg == "--e2b-timeout" and i + 1 < len(args):
            config.timeout = int(args[i + 1])
            i += 1
        elif arg == "--e2b-cpu" and i + 1 < len(args):
            config.cpu = int(args[i + 1])
            i += 1
        elif arg == "--e2b-mem" and i + 1 < len(args):
            config.mem_gb = int(args[i + 1])
            i += 1
        elif arg == "--e2b-env" and i + 1 < len(args):
            # Parse KEY=VALUE
            env_str = args[i + 1]
            if "=" in env_str:
                key, value = env_str.split("=", 1)
                config.env_vars[key] = value
            i += 1
        elif arg == "--e2b-env-from" and i + 1 < len(args):
            # Load from .env file
            env_file = Path(args[i + 1])
            if env_file.exists():
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            # Remove quotes if present
                            value = value.strip('"').strip("'")
                            config.env_vars[key] = value
            i += 1
        elif arg == "--e2b-pass-env" and i + 1 < len(args):
            # Pass through from current environment
            env_name = args[i + 1]
            if env_name in os.environ:
                config.env_vars[env_name] = os.environ[env_name]
            i += 1
        elif arg == "--dry-run":
            config.dry_run = True
        else:
            remaining_args.append(arg)

        i += 1

    return config, remaining_args


def add_e2b_help_text(help_lines: List[str]) -> None:
    """Add E2B-specific help text to run command help."""
    e2b_help = [
        "",
        "[bold blue]🚀 E2B Remote Execution[/bold blue]",
        "  [cyan]--e2b[/cyan]             Execute in E2B sandbox (requires E2B_API_KEY)",
        "  [cyan]--e2b-timeout[/cyan]     Timeout in seconds (default: 900)",
        "  [cyan]--e2b-cpu[/cyan]         CPU cores (default: 2)",
        "  [cyan]--e2b-mem[/cyan]         Memory in GB (default: 4)",
        "  [cyan]--e2b-env[/cyan]         Set env var (KEY=VALUE, repeatable)",
        "  [cyan]--e2b-env-from[/cyan]    Load env vars from file",
        "  [cyan]--e2b-pass-env[/cyan]    Pass env var from current shell (repeatable)",
        "  [cyan]--dry-run[/cyan]         Show what would be sent without executing",
        "",
        "  [dim]# Example: Run in E2B with Supabase credentials[/dim]",
        "  [green]osiris run pipeline.yaml --e2b \\[/green]",
        "  [green]  --e2b-pass-env SUPABASE_URL \\[/green]",
        "  [green]  --e2b-pass-env SUPABASE_SERVICE_ROLE_KEY[/green]",
    ]
    help_lines.extend(e2b_help)


def execute_remote(
    manifest_path: Path,
    session_dir: Path,
    e2b_config: E2BConfig,
    run_config: RunConfig,
    use_json: bool = False,
) -> bool:
    """Execute pipeline remotely in E2B sandbox.

    Args:
        manifest_path: Path to compiled manifest
        session_dir: Session directory for logs
        e2b_config: E2B configuration
        run_config: Runtime configuration
        use_json: Whether to output JSON

    Returns:
        True if execution succeeded
    """
    from rich.console import Console

    console = Console()

    try:
        # Phase 1: Prepare payload
        log_event("e2b.prepare.start")
        prepare_start = time.time()

        build_dir = session_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)

        builder = PayloadBuilder(session_dir, build_dir)

        if e2b_config.dry_run:
            # Validate and show what would be sent
            payload_path = builder.build(manifest_path, run_config)
            manifest = builder.validate_payload(payload_path)

            if use_json:
                print(
                    json.dumps(
                        {
                            "dry_run": True,
                            "payload": {
                                "files": manifest.files,
                                "size_bytes": manifest.total_size_bytes,
                                "sha256": manifest.sha256,
                            },
                            "env_vars": list(e2b_config.env_vars.keys()),
                            "resources": {
                                "cpu": e2b_config.cpu,
                                "mem_gb": e2b_config.mem_gb,
                                "timeout": e2b_config.timeout,
                            },
                        },
                        indent=2,
                    )
                )
            else:
                console.print("\n[bold]Dry Run - Would execute with:[/bold]")
                console.print(f"  Payload size: {manifest.total_size_bytes} bytes")
                console.print(f"  SHA256: {manifest.sha256}")
                console.print(f"  Files: {', '.join(f['name'] for f in manifest.files)}")
                console.print(f"  Environment: {', '.join(e2b_config.env_vars.keys())}")
                console.print(f"  Resources: {e2b_config.cpu} CPU, {e2b_config.mem_gb}GB RAM")
                console.print(f"  Timeout: {e2b_config.timeout}s")

            log_event(
                "e2b.prepare.finish",
                duration=time.time() - prepare_start,
                sha256=manifest.sha256,
                size_bytes=manifest.total_size_bytes,
            )
            return True

        # Build actual payload
        payload_path = builder.build(manifest_path, run_config)
        manifest = builder.validate_payload(payload_path)

        log_event(
            "e2b.prepare.finish",
            duration=time.time() - prepare_start,
            sha256=manifest.sha256,
            size_bytes=manifest.total_size_bytes,
        )
        log_metric("e2b.payload.size", manifest.total_size_bytes, unit="bytes")

        # Initialize E2B client
        client = E2BClient()

        # Phase 2: Create sandbox and upload
        log_event("e2b.upload.start")
        upload_start = time.time()

        if not use_json:
            console.print("[cyan]Creating E2B sandbox... [/cyan]", end="")

        handle = client.create_sandbox(
            cpu=e2b_config.cpu,
            mem_gb=e2b_config.mem_gb,
            env=e2b_config.env_vars,
            timeout=e2b_config.timeout,
        )

        if not use_json:
            console.print("[green]✓[/green]")
            console.print("[cyan]Uploading payload... [/cyan]", end="")

        client.upload_payload(handle, payload_path)

        log_event(
            "e2b.upload.finish", duration=time.time() - upload_start, sandbox_id=handle.sandbox_id
        )

        if not use_json:
            console.print("[green]✓[/green]")
            console.print("[cyan]Executing remotely... [/cyan]", end="")

        # Phase 3: Execute
        log_event("e2b.exec.start", sandbox_id=handle.sandbox_id)
        exec_start = time.time()

        # Start execution
        process_id = client.start(handle, ["python", "mini_runner.py"])

        # Poll until complete
        final_status = client.poll_until_complete(handle, process_id, e2b_config.timeout)

        exec_duration = time.time() - exec_start
        log_event(
            "e2b.exec.finish",
            duration=exec_duration,
            status=final_status.status.value,
            exit_code=final_status.exit_code,
        )
        log_metric("e2b.exec.duration", exec_duration, unit="seconds")

        if final_status.status == SandboxStatus.TIMEOUT:
            log_event("e2b.timeout", duration=exec_duration)
            if not use_json:
                console.print("[red]✗ (timeout)[/red]")
            else:
                print(
                    json.dumps(
                        {"status": "error", "error": "Execution timeout", "duration": exec_duration}
                    )
                )
            return False

        if not use_json:
            if final_status.status == SandboxStatus.SUCCESS:
                console.print("[green]✓[/green]")
            else:
                console.print("[red]✗[/red]")
            console.print("[cyan]Downloading artifacts... [/cyan]", end="")

        # Phase 4: Download artifacts
        log_event("e2b.download.start")
        download_start = time.time()

        remote_dir = session_dir / "remote"
        client.download_artifacts(handle, remote_dir)

        log_event("e2b.download.finish", duration=time.time() - download_start)

        if not use_json:
            console.print("[green]✓[/green]")

        # Cleanup
        client.close(handle)

        # Report results
        success = final_status.status == SandboxStatus.SUCCESS

        if use_json:
            print(
                json.dumps(
                    {
                        "status": "success" if success else "error",
                        "sandbox_id": handle.sandbox_id,
                        "exit_code": final_status.exit_code,
                        "duration": exec_duration,
                        "remote_artifacts": str(remote_dir) if remote_dir.exists() else None,
                    }
                )
            )
        else:
            if success:
                console.print("[green]✅ Remote execution completed successfully[/green]")
            else:
                console.print(
                    f"[red]❌ Remote execution failed (exit code: {final_status.exit_code})[/red]"
                )

            if remote_dir.exists():
                console.print(f"[dim]Remote artifacts: {remote_dir}[/dim]")

        return success

    except Exception as e:
        log_event("e2b.error", error=str(e))

        if use_json:
            print(json.dumps({"status": "error", "error": str(e)}))
        else:
            # Check for common errors
            if "E2B_API_KEY" in str(e):
                console.print(
                    "[red]❌ E2B auth failed. Check E2B_API_KEY environment variable[/red]"
                )
            else:
                console.print(f"[red]❌ E2B error: {e}[/red]")

        return False
