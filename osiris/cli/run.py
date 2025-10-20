"""CLI command for running pipelines (OML or compiled manifests) with Rich formatting."""

import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from rich.console import Console
import yaml

from ..core.adapter_factory import get_execution_adapter
from ..core.aiop_export import export_aiop_auto
from ..core.compiler_v0 import CompilerV0
from ..core.env_loader import load_env
from ..core.execution_adapter import ExecutionContext
from ..core.session_logging import SessionContext, log_event, log_metric, set_current_session

# Defensive imports for E2B components
try:
    from ..remote.e2b_integration import add_e2b_help_text, parse_e2b_args

    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False

    # Provide fallback implementations
    def add_e2b_help_text(lines):
        lines.append("[dim]E2B support not available (missing dependencies)[/dim]")

    def parse_e2b_args(args):
        # Return minimal config that disables E2B
        class E2BConfig:
            enabled = False
            timeout = 900
            cpu = 2
            mem_gb = 4
            env_vars = {}

        return E2BConfig(), args


console = Console()


def show_run_help(json_output: bool = False):
    """Show formatted help for the run command."""
    if json_output:
        help_data = {
            "command": "run",
            "description": "Execute pipeline (OML or compiled manifest)",
            "usage": "osiris run [OPTIONS] [PIPELINE_FILE]",
            "arguments": {"PIPELINE_FILE": "Path to OML or manifest.yaml file (optional with --last-compile)"},
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
                "osiris run build/pipelines/dev/orders/manifest.yaml",
                "osiris run pipeline.yaml --profile prod",
                "osiris run --last-compile",
                "osiris run --last-compile-in orders_etl",
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
    console.print("  [cyan]--out[/cyan]             Output directory for artifacts (copies after run)")
    console.print("  [cyan]--profile, -p[/cyan]     Active profile for OML (dev, staging, prod)")
    console.print("  [cyan]--param[/cyan]           Set parameters for OML (format: key=value)")
    console.print("  [cyan]--last-compile[/cyan]    Use manifest from most recent successful compile")
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
    console.print("  [green]osiris run build/pipelines/dev/orders/manifest.yaml[/green]")
    console.print()
    console.print("  [dim]# Run last compiled manifest[/dim]")
    console.print("  [green]osiris compile pipeline.yaml[/green]")
    console.print("  [green]osiris run --last-compile[/green]")
    console.print()
    console.print("  [dim]# Run with production profile and parameters[/dim]")
    console.print("  [green]osiris run pipeline.yaml --profile prod --param db=prod_db[/green]")
    console.print()

    console.print("[bold blue]📂 Run Logs Structure[/bold blue]")
    console.print("  [cyan]run_logs/[{profile}/]{pipeline}/{ts}_{run_id}-{hash}/[/cyan]")
    console.print("  ├── osiris.log         # Full execution logs")
    console.print("  ├── events.jsonl       # Structured events")
    console.print("  ├── metrics.jsonl      # Performance metrics")
    console.print("  └── artifacts/         # Execution outputs")
    console.print()


def find_last_compile_manifest(pipeline_slug: str | None = None, profile: str | None = None) -> str | None:
    """Find the manifest from the last successful compile using FilesystemContract.

    Args:
        pipeline_slug: Specific pipeline slug to find. If None, uses global latest.
        profile: Profile name for filtering

    Returns:
        Path to manifest.yaml or None if not found
    """
    from ..core.fs_config import load_osiris_config
    from ..core.fs_paths import FilesystemContract

    try:
        # Load filesystem contract
        fs_config, ids_config, _ = load_osiris_config()
        contract = FilesystemContract(fs_config, ids_config)
        index_paths = contract.index_paths()

        # Determine which latest pointer to use
        if pipeline_slug:
            # Per-pipeline latest pointer
            latest_file = index_paths["latest"] / f"{pipeline_slug}.txt"
        else:
            # Global latest compile pointer
            latest_file = index_paths["base"] / "last_compile.txt"

        if not latest_file.exists():
            return None

        # Read pointer (format: manifest_path on first line)
        with open(latest_file) as f:
            manifest_path_str = f.readline().strip()

        if manifest_path_str and Path(manifest_path_str).exists():
            return manifest_path_str

    except Exception:
        # Fallback: try to find any manifest in build/
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


def execute_with_adapter(
    manifest_data: dict[str, Any],
    target: str,
    adapter_config: dict[str, Any],
    context: ExecutionContext,
    use_json: bool = False,  # noqa: ARG001
    source_manifest_path: str | None = None,
    verbose: bool = False,
) -> tuple[bool, str | None]:
    """Execute pipeline using execution adapters.

    Args:
        manifest_data: Compiled manifest as dict
        target: Execution target ("local" or "e2b")
        adapter_config: Configuration for the adapter
        context: Execution context
        use_json: Whether to use JSON output
        source_manifest_path: Path to original manifest
        verbose: Whether to show step progress on stdout

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Add verbose flag to config
        adapter_config["verbose"] = verbose

        # Get adapter from factory
        adapter = get_execution_adapter(target, adapter_config)
        log_event("adapter_selected", adapter=target, session_id=context.session_id)

        # Phase 1: Prepare execution
        log_event("adapter_prepare_start", session_id=context.session_id)

        # Pass source manifest location for cfg resolution
        if source_manifest_path:
            prepared_metadata = manifest_data.get("metadata", {})
            prepared_metadata["source_manifest_path"] = source_manifest_path
            manifest_data["metadata"] = prepared_metadata

        prepared = adapter.prepare(manifest_data, context)
        log_event("adapter_prepare_complete", session_id=context.session_id)

        # Phase 2: Execute
        log_event("adapter_execute_start", session_id=context.session_id)
        result = adapter.execute(prepared, context)
        log_event("adapter_execute_complete", success=result.success, session_id=context.session_id)

        # Phase 3: Collect artifacts
        log_event("adapter_collect_start", session_id=context.session_id)
        _ = adapter.collect(prepared, context)
        log_event("adapter_collect_complete", session_id=context.session_id)

        # Log final metrics
        log_metric("adapter_execution_duration", result.duration_seconds, unit="seconds")
        log_metric("adapter_exit_code", result.exit_code, unit="code")

        return result.success, result.error_message

    except Exception as e:
        error_msg = f"Adapter execution failed: {e}"
        log_event("adapter_execution_error", error=error_msg, session_id=context.session_id)
        return False, error_msg


def run_command(args: list[str]):
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
        elif pipeline_file is None:
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

        # Find the last compile manifest using FilesystemContract pointers
        # last_compile_in is treated as pipeline_slug if provided
        pipeline_file = find_last_compile_manifest(pipeline_slug=last_compile_in, profile=profile)

        if not pipeline_file:
            # Try environment variable as fallback
            if last_compile and "OSIRIS_LAST_MANIFEST" in os.environ:
                pipeline_file = os.environ["OSIRIS_LAST_MANIFEST"]

            if not pipeline_file:
                error_msg = "No recent compile found"
                if last_compile_in:
                    error_msg += f" for pipeline '{last_compile_in}'"
                else:
                    error_msg += " (check .osiris/index/latest/ or run 'osiris compile' first)"

                if use_json:
                    print(json.dumps({"error": error_msg}))
                else:
                    console.print(f"[red]❌ {error_msg}[/red]")
                    console.print("[dim]💡 Run 'osiris compile <pipeline>' first to create a manifest[/dim]")
                sys.exit(2)

        # Force this to be treated as a manifest
        file_type = "manifest"
    else:
        # Check if pipeline file was provided
        if not pipeline_file:
            error_msg = "No pipeline file specified"
            if use_json:
                print(json.dumps({"error": error_msg, "usage": "osiris run [PIPELINE_FILE | --last-compile]"}))
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

    # Load FilesystemContract for session creation
    from ..core.fs_config import load_osiris_config
    from ..core.fs_paths import FilesystemContract
    from ..core.run_ids import RunIdGenerator
    from ..core.run_index import RunIndexWriter

    fs_config, ids_config, _ = load_osiris_config()
    contract = FilesystemContract(fs_config, ids_config)

    # Resolve profile to default if None
    if profile is None and fs_config.profiles.enabled:
        profile = fs_config.profiles.default

    # Generate run ID (will be updated with pipeline_slug after we know it)
    from ..core.run_ids import CounterStore

    counter_store = CounterStore(contract.index_paths()["counters"])
    run_id_gen = RunIdGenerator(
        run_id_format=(
            ids_config.run_id_format if isinstance(ids_config.run_id_format, list) else [ids_config.run_id_format]
        ),
        counter_store=counter_store,
    )

    # Temporary session (we'll create proper one after knowing pipeline_slug)
    session_id = f"run_{int(time.time() * 1000)}"
    # Use filesystem contract to determine logs directory
    temp_logs_dir = fs_config.resolve_path(fs_config.run_logs_dir)
    session = SessionContext(session_id=session_id, base_logs_dir=temp_logs_dir)
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
        session_artifacts_dir = session.session_dir / "artifacts"
        session_artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Compile if needed
        if file_type == "oml":
            log_event("compile_start", pipeline=pipeline_file)
            compile_start = time.time()

            # Extract pipeline slug from OML
            with open(pipeline_file) as f:
                oml_data = yaml.safe_load(f)
            pipeline_slug = oml_data.get("pipeline", {}).get("id", Path(pipeline_file).stem)

            # Use FilesystemContract for compilation (writes to build/ directory)
            compiler = CompilerV0(fs_contract=contract, pipeline_slug=pipeline_slug)
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
                                "session_dir": str(session.session_dir),
                            }
                        )
                    )
                else:
                    console.print(f"[red]❌ Compilation failed: {compile_message}[/red]")
                    console.print(f"[dim]Session: {session.session_dir}/[/dim]")
                sys.exit(2)

            log_event("compile_complete", message=compile_message, duration=compile_duration)

            # Get manifest path from compiler via FilesystemContract
            manifest_path = contract.manifest_paths(
                pipeline_slug=pipeline_slug,
                manifest_hash=compiler.manifest_hash,
                manifest_short=compiler.manifest_short,
                profile=profile,
            )["manifest"]

            if not use_json:
                console.print("[green]✓[/green]")
                console.print("[cyan]Executing pipeline... [/cyan]", end="")
        else:
            # Direct manifest execution
            manifest_path = Path(pipeline_file)

        # Phase 2: Execute using adapters
        log_event("adapter_execution_start", manifest=str(manifest_path))

        # Load manifest data for adapter
        with open(manifest_path) as f:
            manifest_data = yaml.safe_load(f)

        # Extract pipeline info from manifest for proper session creation
        pipeline_slug_final = manifest_data.get("pipeline", {}).get("id", "unknown")
        # Get manifest_short from meta (or derive from meta.manifest_hash if missing)
        manifest_short = manifest_data.get("meta", {}).get("manifest_short", "")
        if not manifest_short:
            manifest_hash_temp = manifest_data.get("meta", {}).get("manifest_hash", "")
            manifest_short = manifest_hash_temp[:7] if manifest_hash_temp else ""
        manifest_profile = manifest_data.get("meta", {}).get("profile", profile)

        # Generate run_id now that we know the pipeline
        run_id_final, run_ts = run_id_gen.generate(pipeline_slug_final)

        # Create proper session with FilesystemContract
        proper_session = SessionContext(
            fs_contract=contract,
            pipeline_slug=pipeline_slug_final,
            profile=manifest_profile,
            run_id=run_id_final,
            manifest_short=manifest_short,
        )

        # Clean up temporary session directory (only if it was created)
        temp_session_dir = session.session_dir
        if temp_session_dir.exists() and temp_session_dir != proper_session.session_dir:
            import contextlib
            import shutil

            with contextlib.suppress(Exception):
                shutil.rmtree(temp_session_dir)  # Best effort cleanup

        # Update the global current session
        set_current_session(proper_session)
        session = proper_session

        # Setup logging on the proper session (same settings as temp session)
        session.setup_logging(level=log_level, enable_debug=verbose)

        # Create execution context with session directory as base
        exec_context = ExecutionContext(session_id=run_id_final, base_path=session.session_dir)

        # Prepare E2B config for adapter
        adapter_e2b_config = {}
        if e2b_config.enabled:
            adapter_e2b_config = {
                "timeout": e2b_config.timeout,
                "cpu": e2b_config.cpu,
                "memory": e2b_config.mem_gb,
                "env": e2b_config.env_vars,
                "verbose": verbose,
                "install_deps": e2b_config.install_deps,
            }

        # Execute with selected adapter
        execute_success, error_message = execute_with_adapter(
            manifest_data=manifest_data,
            target=e2b_config.target,
            adapter_config=adapter_e2b_config,
            context=exec_context,
            use_json=use_json,
            source_manifest_path=str(manifest_path),
            verbose=verbose,
        )

        total_duration = time.time() - start_time
        log_metric("total_duration", total_duration, unit="seconds")

        # Copy artifacts to user-specified location if requested
        if output_dir and session_artifacts_dir.exists():
            user_output_dir = Path(output_dir)
            user_output_dir.mkdir(parents=True, exist_ok=True)
            for item in session_artifacts_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, user_output_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, user_output_dir / item.name, dirs_exist_ok=True)

        if execute_success:
            log_event("run_complete", total_duration=total_duration, adapter_execution=True)

            # Extract full manifest hash for index from meta.manifest_hash (not pipeline.fingerprints.manifest_fp)
            manifest_hash = manifest_data.get("meta", {}).get("manifest_hash", "")

            # Write to run index
            try:
                from datetime import datetime

                from ..core.run_index import RunRecord

                # Compute AIOP path for index
                index_profile = manifest_profile or fs_config.profiles.default if fs_config.profiles.enabled else None
                aiop_paths = contract.aiop_paths(
                    pipeline_slug=pipeline_slug_final,
                    manifest_hash=manifest_hash,
                    manifest_short=manifest_short,
                    run_id=run_id_final,
                    profile=index_profile,
                )
                aiop_base_dir = str(aiop_paths["base"])

                # Format run_ts as ISO string
                run_ts_str = run_ts if isinstance(run_ts, str) else (run_ts or datetime.utcnow()).isoformat()

                # Create run record
                record = RunRecord(
                    run_id=run_id_final,
                    pipeline_slug=pipeline_slug_final,
                    profile=index_profile,
                    manifest_hash=manifest_hash,
                    manifest_short=manifest_short,
                    run_ts=run_ts_str,
                    status="success",
                    duration_ms=int(total_duration * 1000),
                    run_logs_path=str(session.session_dir),
                    aiop_path=aiop_base_dir,
                    build_manifest_path=str(manifest_path),
                    tags=[],
                )

                index_writer = RunIndexWriter(contract.index_paths()["base"])
                index_writer.append(record)
                log_event("run_index_updated", run_id=run_id_final)
            except Exception as e:
                # Best-effort, don't fail the run
                log_event("run_index_error", error=str(e))

            if not use_json:
                console.print("[green]✓[/green]")

            execution_type = "E2B" if e2b_config.enabled else "local"

            if use_json:
                result = {
                    "status": "success",
                    "message": f"Pipeline executed successfully ({execution_type})",
                    "session_id": session_id,
                    "session_dir": str(session.session_dir),
                    "artifacts_dir": output_dir if output_dir else str(session.session_dir / "artifacts"),
                    "execution_type": execution_type,
                    "duration": {"total": round(total_duration, 2)},
                }
                if file_type == "oml":
                    result["duration"]["compile"] = round(compile_duration, 2)
                    result["compiled_dir"] = str(session.session_dir / "compiled")
                print(json.dumps(result))
            else:
                console.print(f"[green]✓ Pipeline completed ({execution_type})[/green]")
                console.print(f"Session: {session.session_dir}/")
                if output_dir:
                    console.print(f"Artifacts copied to: {output_dir}/")

            sys.exit(0)
        else:
            log_event("run_error", phase="execute", error=error_message, duration=total_duration)

            if not use_json:
                console.print("[red]✗[/red]")

            if use_json:
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "phase": "execute",
                            "message": error_message or "Pipeline execution failed",
                            "session_id": session_id,
                            "session_dir": str(session.session_dir),
                        }
                    )
                )
            else:
                console.print(f"[red]❌ {error_message or 'Pipeline execution failed'}[/red]")
                console.print(f"Session: {session.session_dir}/")

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
                        "session_dir": str(session.session_dir),
                    }
                )
            )
        else:
            console.print(f"[red]❌ {error_msg}[/red]")
            console.print(f"Session: {session.session_dir}/")

        sys.exit(1)

    finally:
        # Export AIOP if enabled (best-effort)
        try:
            # Determine final status
            if "execute_success" in locals() and execute_success:
                final_status = "completed"
            elif "compile_success" in locals() and not compile_success:
                final_status = "failed_compile"
            else:
                final_status = "failed"

            # Get manifest hash and pipeline info if available
            manifest_hash = None
            pipeline_slug_aiop = None
            manifest_short_aiop = None
            run_id_aiop = None
            if "manifest_data" in locals() and isinstance(manifest_data, dict):
                # Manifest hash is at meta.manifest_hash (pure hex, no algorithm prefix)
                manifest_hash = manifest_data.get("meta", {}).get("manifest_hash", "")
                pipeline_slug_aiop = manifest_data.get("pipeline", {}).get("id")
                # Derive manifest_short from manifest_hash, or use meta.manifest_short if available
                manifest_short_aiop = manifest_data.get("meta", {}).get("manifest_short") or (
                    manifest_hash[:7] if manifest_hash else ""
                )
                if "run_id_final" in locals():
                    run_id_aiop = run_id_final

            # Export AIOP
            export_success, export_error = export_aiop_auto(
                session_id=session_id,
                manifest_hash=manifest_hash,
                status=final_status,
                end_time=datetime.utcnow(),
                fs_contract=contract if "contract" in locals() else None,
                pipeline_slug=pipeline_slug_aiop,
                profile=profile,
                run_id=run_id_aiop,
                manifest_short=manifest_short_aiop,
                session_dir=session.session_dir,
            )

            if not export_success:
                log_event("aiop_export_error", error=export_error, session_id=session_id)
        except Exception as e:
            # Best-effort, don't fail the run
            log_event("aiop_export_error", error=str(e), session_id=session_id)

        # Clean up session
        session.close()
        set_current_session(None)
