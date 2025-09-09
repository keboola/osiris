"""CLI command for running pipelines (OML or compiled manifests) with Rich formatting."""

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional

import yaml
from rich.console import Console

from ..core.compiler_v0 import CompilerV0
from ..core.env_loader import load_env
from ..core.runner_v0 import RunnerV0
from ..core.session_logging import SessionContext, log_event, log_metric, set_current_session
from ..remote.e2b_integration import add_e2b_help_text, execute_remote, parse_e2b_args
from ..remote.e2b_pack import RunConfig

console = Console()


def show_run_help(json_output: bool = False):
    """Show formatted help for the run command."""
    if json_output:
        help_data = {
            "command": "run",
            "description": "Execute pipeline (OML or compiled manifest)",
            "usage": "osiris run [OPTIONS] [PIPELINE_FILE]",
            "arguments": {
                "PIPELINE_FILE": "Path to OML or manifest.yaml file (optional with --last-compile)"
            },
            "options": {
                "--out": "Output directory for artifacts (default: session directory)",
                "--profile": "Active profile for OML compilation (dev, staging, prod)",
                "--param": "Set parameters for OML (format: key=value, repeatable)",
                "--last-compile": "Use manifest from most recent successful compile",
                "--last-compile-in": "Find latest compile in specified directory",
                "--verbose": "Show detailed execution logs",
                "--json": "Output in JSON format",
                "--help": "Show this help message",
                "--e2b": "Execute in E2B sandbox (requires E2B_API_KEY)",
                "--e2b-timeout": "Timeout in seconds (default: 900)",
                "--e2b-cpu": "CPU cores (default: 2)",
                "--e2b-mem": "Memory in GB (default: 4)",
                "--e2b-env": "Set env var (KEY=VALUE, repeatable)",
                "--e2b-env-from": "Load env vars from file",
                "--e2b-pass-env": "Pass env var from current shell (repeatable)",
                "--dry-run": "Show what would be sent without executing",
            },
            "examples": [
                "osiris run pipeline.yaml",
                "osiris run compiled/manifest.yaml",
                "osiris run pipeline.yaml --profile prod",
                "osiris run --last-compile",
                "osiris run --last-compile-in logs/",
                "osiris run pipeline.yaml --param db=mydb --out /tmp/results",
            ],
        }
        print(json.dumps(help_data, indent=2))
        return

    console.print()
    console.print("[bold green]osiris run - Execute Pipeline[/bold green]")
    console.print("🚀 Execute OML pipelines or compiled manifests with session tracking")
    console.print()

    console.print("[bold]Usage:[/bold] osiris run [OPTIONS] [PIPELINE_FILE]")
    console.print()

    console.print("[bold blue]📖 What this does[/bold blue]")
    console.print("  • For OML files: Compiles then executes in one session")
    console.print("  • For manifests: Executes directly")
    console.print("  • Creates session directory with full audit trail")
    console.print("  • Routes all logs to session, keeps stdout clean")
    console.print("  • Supports convenient --last-compile flags")
    console.print()

    console.print("[bold blue]📁 Arguments[/bold blue]")
    console.print("  [cyan]PIPELINE_FILE[/cyan]     Path to OML or manifest.yaml file")
    console.print("                      Optional when using --last-compile flags")
    console.print()

    console.print("[bold blue]⚙️  Options[/bold blue]")
    console.print(
        "  [cyan]--out[/cyan]             Output directory for artifacts (copies after run)"
    )
    console.print("  [cyan]--profile, -p[/cyan]     Active profile for OML (dev, staging, prod)")
    console.print("  [cyan]--param[/cyan]           Set parameters for OML (format: key=value)")
    console.print(
        "  [cyan]--last-compile[/cyan]    Use manifest from most recent successful compile"
    )
    console.print("  [cyan]--last-compile-in[/cyan] Find latest compile in specified directory")
    console.print("  [cyan]--verbose[/cyan]         Show single-line event summaries on stdout")
    console.print("  [cyan]--json[/cyan]            Output in JSON format")
    console.print("  [cyan]--help[/cyan]            Show this help message")
    console.print()

    # Add E2B help section
    help_lines = []
    add_e2b_help_text(help_lines)
    for line in help_lines:
        console.print(line)
    console.print()

    console.print("[bold blue]💡 Examples[/bold blue]")
    console.print("  [dim]# Run OML pipeline (compile + execute)[/dim]")
    console.print("  [green]osiris run pipeline.yaml[/green]")
    console.print()
    console.print("  [dim]# Run pre-compiled manifest[/dim]")
    console.print("  [green]osiris run logs/compile_123/compiled/manifest.yaml[/green]")
    console.print()
    console.print("  [dim]# Run last compiled manifest[/dim]")
    console.print("  [green]osiris compile pipeline.yaml[/green]")
    console.print("  [green]osiris run --last-compile[/green]")
    console.print()
    console.print("  [dim]# Run with production profile and parameters[/dim]")
    console.print("  [green]osiris run pipeline.yaml --profile prod --param db=prod_db[/green]")
    console.print()

    console.print("[bold blue]📂 Session Structure[/bold blue]")
    console.print("  [cyan]logs/run_<timestamp>/[/cyan]")
    console.print("  ├── osiris.log         # Full execution logs")
    console.print("  ├── events.jsonl       # Structured events")
    console.print("  ├── compiled/          # If OML input")
    console.print("  │   └── manifest.yaml")
    console.print("  └── artifacts/         # Execution outputs")
    console.print()


def find_last_compile_manifest(logs_dir: Optional[str] = None) -> Optional[str]:
    """Find the manifest from the last successful compile.

    Args:
        logs_dir: Directory to search for compile sessions. If None, uses logs/.last_compile.json

    Returns:
        Path to manifest.yaml or None if not found
    """
    if logs_dir:
        # Find latest compile_* session in specified directory
        logs_path = Path(logs_dir)
        if not logs_path.exists():
            return None

        compile_sessions = []
        for session_dir in logs_path.iterdir():
            if session_dir.is_dir() and session_dir.name.startswith("compile_"):
                # Check if it has a compiled manifest
                manifest_path = session_dir / "compiled" / "manifest.yaml"
                if manifest_path.exists():
                    compile_sessions.append((session_dir.stat().st_mtime, str(manifest_path)))

        if compile_sessions:
            # Return the most recent one
            compile_sessions.sort(reverse=True)
            return compile_sessions[0][1]
    else:
        # Use the pointer file
        pointer_file = Path("logs") / ".last_compile.json"
        if pointer_file.exists():
            try:
                with open(pointer_file) as f:
                    pointer_data = json.load(f)
                manifest_path = pointer_data.get("manifest_path")
                if manifest_path and Path(manifest_path).exists():
                    return manifest_path
            except (json.JSONDecodeError, KeyError):
                pass

    return None


def detect_file_type(file_path: str) -> str:
    """Detect if file is OML or compiled manifest.

    Returns:
        'oml' or 'manifest'
    """
    try:
        with open(file_path) as f:
            content = yaml.safe_load(f)

        # A manifest has 'pipeline', 'steps', and 'meta' at the top level
        is_manifest = all(key in content for key in ["pipeline", "steps", "meta"])

        # An OML file has 'oml_version' or 'name' and 'steps' without 'meta'
        is_oml = ("oml_version" in content or "name" in content) and "meta" not in content

        if is_manifest and not is_oml:
            return "manifest"
        else:
            return "oml"
    except Exception:
        # Default to OML if we can't parse
        return "oml"


def run_command(args: List[str]):
    """Execute the run command."""
    # Load environment variables (redundant but safe)
    loaded_envs = load_env()

    # Check for help flag
    if "--help" in args or "-h" in args:
        json_mode = "--json" in args
        show_run_help(json_output=json_mode)
        return

    # Parse E2B arguments first
    e2b_config, remaining_args = parse_e2b_args(args)

    # Parse remaining arguments manually
    pipeline_file = None
    profile = None
    params = {}
    output_dir = None  # None means use session directory
    verbose = False
    use_json = "--json" in remaining_args
    last_compile = False
    last_compile_in = None

    i = 0
    while i < len(remaining_args):
        arg = remaining_args[i]

        if arg.startswith("--"):
            if arg == "--out":
                if i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("--"):
                    output_dir = remaining_args[i + 1]
                    i += 1
                else:
                    error_msg = "Option --out requires a value"
                    if use_json:
                        print(json.dumps({"error": error_msg}))
                    else:
                        console.print(f"[red]❌ {error_msg}[/red]")
                    sys.exit(2)

            elif arg in ("--profile", "-p"):
                if i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("--"):
                    profile = remaining_args[i + 1]
                    i += 1
                else:
                    error_msg = "Option --profile requires a value"
                    if use_json:
                        print(json.dumps({"error": error_msg}))
                    else:
                        console.print(f"[red]❌ {error_msg}[/red]")
                    sys.exit(2)

            elif arg == "--param":
                if i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("--"):
                    param_str = remaining_args[i + 1]
                    if "=" in param_str:
                        key, value = param_str.split("=", 1)
                        params[key] = value
                    else:
                        error_msg = f"Invalid parameter format: {param_str} (expected key=value)"
                        if use_json:
                            print(json.dumps({"error": error_msg}))
                        else:
                            console.print(f"[red]❌ {error_msg}[/red]")
                        sys.exit(2)
                    i += 1
                else:
                    error_msg = "Option --param requires a value"
                    if use_json:
                        print(json.dumps({"error": error_msg}))
                    else:
                        console.print(f"[red]❌ {error_msg}[/red]")
                    sys.exit(2)

            elif arg == "--last-compile":
                last_compile = True

            elif arg == "--last-compile-in":
                if i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("--"):
                    last_compile_in = remaining_args[i + 1]
                    i += 1
                else:
                    # Check environment variable
                    last_compile_in = os.environ.get("OSIRIS_LAST_COMPILE_DIR", "logs")

            elif arg == "--verbose":
                verbose = True

            elif arg == "--json":
                use_json = True

            else:
                error_msg = f"Unknown option: {arg}"
                if use_json:
                    print(json.dumps({"error": error_msg}))
                else:
                    console.print(f"[red]❌ {error_msg}[/red]")
                    console.print("[dim]💡 Run 'osiris run --help' to see available options[/dim]")
                sys.exit(2)
        else:
            if pipeline_file is None:
                pipeline_file = arg
            else:
                error_msg = "Multiple pipeline files specified"
                if use_json:
                    print(json.dumps({"error": error_msg}))
                else:
                    console.print(f"[red]❌ {error_msg}[/red]")
                    console.print("[dim]💡 Only one pipeline file can be processed at a time[/dim]")
                sys.exit(2)

        i += 1

    # Handle last-compile flags
    if last_compile or last_compile_in:
        if pipeline_file:
            error_msg = "Cannot specify both a pipeline file and --last-compile flags"
            if use_json:
                print(json.dumps({"error": error_msg}))
            else:
                console.print(f"[red]❌ {error_msg}[/red]")
            sys.exit(2)

        # Find the last compile manifest
        pipeline_file = find_last_compile_manifest(last_compile_in)

        if not pipeline_file:
            # Try environment variable as fallback
            if last_compile and "OSIRIS_LAST_MANIFEST" in os.environ:
                pipeline_file = os.environ["OSIRIS_LAST_MANIFEST"]

            if not pipeline_file:
                error_msg = "No recent compile found"
                if last_compile_in:
                    error_msg += f" in {last_compile_in}"
                else:
                    error_msg += " (no logs/.last_compile.json found)"

                if use_json:
                    print(json.dumps({"error": error_msg}))
                else:
                    console.print(f"[red]❌ {error_msg}[/red]")
                    console.print("[dim]💡 Run 'osiris compile' first to create a manifest[/dim]")
                sys.exit(2)

        # Force this to be treated as a manifest
        file_type = "manifest"
    else:
        # Check if pipeline file was provided
        if not pipeline_file:
            error_msg = "No pipeline file specified"
            if use_json:
                print(
                    json.dumps(
                        {"error": error_msg, "usage": "osiris run [PIPELINE_FILE | --last-compile]"}
                    )
                )
            else:
                console.print(f"[red]❌ {error_msg}[/red]")
                console.print("[dim]💡 Run 'osiris run --help' to see usage examples[/dim]")
            sys.exit(2)

        # Check if file exists
        if not Path(pipeline_file).exists():
            error_msg = f"Pipeline file not found: {pipeline_file}"
            if use_json:
                print(json.dumps({"error": error_msg}))
            else:
                console.print(f"[red]❌ {error_msg}[/red]")
            sys.exit(2)

        # Detect file type
        file_type = detect_file_type(pipeline_file)

    # Create a run session
    session_id = f"run_{int(time.time() * 1000)}"
    session = SessionContext(session_id=session_id, base_logs_dir=Path("logs"))
    set_current_session(session)

    # Log loaded env files (masked paths)
    if loaded_envs:
        log_event("env_loaded", files=[str(p) for p in loaded_envs])

    # Setup logging to session (not stdout)
    import logging

    # Remove console handlers from root logger
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)

    # Setup session logging (file only)
    log_level = logging.DEBUG if verbose else logging.INFO
    session.setup_logging(level=log_level, enable_debug=verbose)

    try:
        # Log run start
        log_event(
            "run_start",
            pipeline=pipeline_file,
            file_type=file_type,
            profile=profile,
            params=params,
            output_dir=output_dir,
            last_compile=last_compile or bool(last_compile_in),
        )

        start_time = time.time()

        if not use_json:
            if file_type == "oml":
                console.print("[cyan]Compiling OML... [/cyan]", end="")
            console.print("[cyan]Executing pipeline... [/cyan]", end="")

        # Determine paths
        session_compiled_dir = session.session_dir / "compiled"
        session_artifacts_dir = session.session_dir / "artifacts"
        session_artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Compile if needed
        if file_type == "oml":
            log_event("compile_start", pipeline=pipeline_file)
            compile_start = time.time()

            session_compiled_dir.mkdir(parents=True, exist_ok=True)
            compiler = CompilerV0(output_dir=str(session_compiled_dir))
            compile_success, compile_message = compiler.compile(
                oml_path=pipeline_file, profile=profile, cli_params=params
            )

            compile_duration = time.time() - compile_start
            log_metric("compilation_duration", compile_duration, unit="seconds")

            if not compile_success:
                log_event("compile_error", error=compile_message, duration=compile_duration)

                if not use_json:
                    console.print("[red]✗[/red]")

                if use_json:
                    print(
                        json.dumps(
                            {
                                "status": "error",
                                "phase": "compile",
                                "message": compile_message,
                                "session_id": session_id,
                                "session_dir": f"logs/{session_id}",
                            }
                        )
                    )
                else:
                    console.print(f"[red]❌ Compilation failed: {compile_message}[/red]")
                    console.print(f"[dim]Session: logs/{session_id}/[/dim]")
                sys.exit(2)

            log_event("compile_complete", message=compile_message, duration=compile_duration)
            manifest_path = session_compiled_dir / "manifest.yaml"

            if not use_json:
                console.print("[green]✓[/green]")
                console.print("[cyan]Executing pipeline... [/cyan]", end="")
        else:
            # Direct manifest execution
            manifest_path = Path(pipeline_file)

        # Phase 2: Check for E2B execution
        if e2b_config.enabled:
            # Execute remotely in E2B
            run_config = RunConfig()
            success = execute_remote(
                manifest_path=manifest_path,
                session_dir=session.session_dir,
                e2b_config=e2b_config,
                run_config=run_config,
                use_json=use_json,
            )
            
            total_duration = time.time() - start_time
            log_metric("total_duration", total_duration, unit="seconds")
            
            if success:
                log_event("run_complete", total_duration=total_duration, remote_execution=True)
                
                if use_json:
                    result = {
                        "status": "success",
                        "message": "Pipeline executed successfully in E2B",
                        "session_id": session_id,
                        "session_dir": f"logs/{session_id}",
                        "remote_execution": True,
                        "duration": {"total": round(total_duration, 2)},
                    }
                    if file_type == "oml":
                        result["duration"]["compile"] = round(compile_duration, 2)
                        result["compiled_dir"] = f"logs/{session_id}/compiled"
                    print(json.dumps(result))
                else:
                    console.print("[green]✅ Remote execution completed successfully[/green]")
                    console.print(f"Session: logs/{session_id}/")
                
                sys.exit(0)
            else:
                log_event("run_error", phase="e2b", error="Remote execution failed", duration=total_duration)
                
                if use_json:
                    print(json.dumps({
                        "status": "error",
                        "phase": "e2b", 
                        "message": "Remote execution failed",
                        "session_id": session_id,
                        "session_dir": f"logs/{session_id}",
                    }))
                else:
                    console.print("[red]❌ Remote execution failed[/red]")
                    console.print(f"Session: logs/{session_id}/")
                
                sys.exit(1)

        # Phase 2: Execute locally
        log_event("execute_start", manifest=str(manifest_path))
        execute_start = time.time()

        runner = RunnerV0(manifest_path=str(manifest_path), output_dir=str(session_artifacts_dir))

        # If verbose, show events as they happen
        if verbose and not use_json:
            original_log = runner._log_event

            def verbose_log(event_type, data):
                result = original_log(event_type, data)
                if event_type == "step_start":
                    console.print(f"[dim]  → Step: {data.get('step_id', 'unknown')}[/dim]")
                elif event_type == "step_complete":
                    console.print(
                        f"[dim]  ✓ Step: {data.get('step_id', 'unknown')} completed[/dim]"
                    )
                return result

            runner._log_event = verbose_log

        execute_success = runner.run()

        execute_duration = time.time() - execute_start
        log_metric("execution_duration", execute_duration, unit="seconds")

        total_duration = time.time() - start_time
        log_metric("total_duration", total_duration, unit="seconds")

        # Copy artifacts to user-specified location if requested
        if output_dir:
            user_output_dir = Path(output_dir)
            user_output_dir.mkdir(parents=True, exist_ok=True)
            for item in session_artifacts_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, user_output_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, user_output_dir / item.name, dirs_exist_ok=True)

        if execute_success:
            log_event(
                "run_complete",
                total_duration=total_duration,
                steps_executed=len([e for e in runner.events if e["type"] == "step_complete"]),
            )

            if not use_json:
                console.print("[green]✓[/green]")

            step_count = sum(1 for e in runner.events if e["type"] == "step_complete")

            if use_json:
                result = {
                    "status": "success",
                    "message": "Pipeline executed successfully",
                    "session_id": session_id,
                    "session_dir": f"logs/{session_id}",
                    "artifacts_dir": output_dir if output_dir else f"logs/{session_id}/artifacts",
                    "steps_executed": step_count,
                    "duration": {"total": round(total_duration, 2)},
                }
                if file_type == "oml":
                    result["duration"]["compile"] = round(compile_duration, 2)
                    result["duration"]["execute"] = round(execute_duration, 2)
                    result["compiled_dir"] = f"logs/{session_id}/compiled"
                print(json.dumps(result))
            else:
                console.print(f"[green]✓ {step_count} steps completed[/green]")
                console.print(f"Session: logs/{session_id}/")
                if output_dir:
                    console.print(f"Artifacts copied to: {output_dir}/")

            sys.exit(0)
        else:
            # Find error details
            error_events = [e for e in runner.events if e["type"] in ("step_error", "run_error")]
            error_msg = "Pipeline execution failed"
            if error_events:
                last_error = error_events[-1]["data"]
                if "error" in last_error:
                    error_msg = last_error["error"]
                elif "message" in last_error:
                    error_msg = last_error["message"]

            log_event("run_error", phase="execute", error=error_msg, duration=total_duration)

            if not use_json:
                console.print("[red]✗[/red]")

            if use_json:
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "phase": "execute",
                            "message": error_msg,
                            "session_id": session_id,
                            "session_dir": f"logs/{session_id}",
                        }
                    )
                )
            else:
                console.print(f"[red]❌ {error_msg}[/red]")
                console.print(f"Session: logs/{session_id}/")

            sys.exit(1)

    except Exception as e:
        # Handle unexpected errors
        error_msg = f"Unexpected error: {str(e)}"
        log_event("run_error", error=error_msg)

        if not use_json:
            console.print("[red]✗[/red]")

        if use_json:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": error_msg,
                        "session_id": session_id,
                        "session_dir": f"logs/{session_id}",
                    }
                )
            )
        else:
            console.print(f"[red]❌ {error_msg}[/red]")
            console.print(f"Session: logs/{session_id}/")

        sys.exit(1)

    finally:
        # Clean up session
        session.close()
        set_current_session(None)
