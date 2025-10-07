"""CLI command for compiling OML to manifest with Rich formatting."""

from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import time

from rich.console import Console

from ..core.compiler_v0 import CompilerV0
from ..core.env_loader import load_env
from ..core.session_logging import SessionContext, log_event, log_metric, set_current_session

console = Console()


def show_compile_help(json_output: bool = False):
    """Show formatted help for the compile command."""
    if json_output:
        help_data = {
            "command": "compile",
            "description": "Compile OML pipeline to deterministic manifest",
            "usage": "osiris compile [OPTIONS] PIPELINE_FILE",
            "arguments": {"PIPELINE_FILE": "Path to the OML pipeline YAML file"},
            "options": {
                "--out": "Output directory for compiled artifacts (default: compiled/)",
                "--profile": "Active profile (e.g., dev, prod)",
                "--param": "Set parameters (format: key=value, can be repeated)",
                "--compile": "Compilation mode: auto|force|never (default: auto)",
                "--json": "Output in JSON format",
                "--help": "Show this help message",
            },
            "examples": [
                "osiris compile pipeline.yaml",
                "osiris compile pipeline.yaml --profile prod",
                "osiris compile pipeline.yaml --param db=mydb --param env=staging",
                "osiris compile pipeline.yaml --out /tmp/compiled --compile force",
            ],
        }
        print(json.dumps(help_data, indent=2))
        return

    console.print()
    console.print("[bold cyan]osiris compile - Compile OML to Manifest[/bold cyan]")
    console.print("🔧 Transform OML pipeline definitions into deterministic execution manifests")
    console.print()

    console.print("[bold]Usage:[/bold] osiris compile [OPTIONS] PIPELINE_FILE")
    console.print()

    console.print("[bold blue]📖 What this does[/bold blue]")
    console.print("  • Loads and validates OML pipeline definition")
    console.print("  • Resolves parameters with proper precedence")
    console.print("  • Generates deterministic, secret-free manifest")
    console.print("  • Creates per-step configuration files")
    console.print("  • Computes SHA-256 fingerprints for caching")
    console.print()

    console.print("[bold blue]📁 Arguments[/bold blue]")
    console.print("  [cyan]PIPELINE_FILE[/cyan]     Path to the OML pipeline YAML file")
    console.print("                      Must be valid OML v0.1.0 format")
    console.print()

    console.print("[bold blue]⚙️  Options[/bold blue]")
    console.print("  [cyan]--out[/cyan]             Output directory for compiled artifacts")
    console.print("                      Default: compiled/")
    console.print("  [cyan]--profile, -p[/cyan]     Active profile (dev, staging, prod, etc.)")
    console.print("                      Overrides parameters per profile config")
    console.print("  [cyan]--param[/cyan]           Set parameters (format: key=value)")
    console.print("                      Can be used multiple times")
    console.print("  [cyan]--compile[/cyan]         Compilation mode:")
    console.print("                      • auto: Use cache if available (default)")
    console.print("                      • force: Always recompile")
    console.print("                      • never: Only use cache, fail if not cached")
    console.print("  [cyan]--json[/cyan]            Output in JSON format for programmatic use")
    console.print("  [cyan]--help[/cyan]            Show this help message")
    console.print()

    console.print("[bold blue]💡 Examples[/bold blue]")
    console.print("  [dim]# Basic compilation[/dim]")
    console.print("  [green]osiris compile pipeline.yaml[/green]")
    console.print()
    console.print("  [dim]# Compile with production profile[/dim]")
    console.print("  [green]osiris compile pipeline.yaml --profile prod[/green]")
    console.print()
    console.print("  [dim]# Override parameters[/dim]")
    console.print("  [green]osiris compile pipeline.yaml --param db=mydb --param env=staging[/green]")
    console.print()
    console.print("  [dim]# Force recompilation to custom directory[/dim]")
    console.print("  [green]osiris compile pipeline.yaml --out /tmp/compiled --compile force[/green]")
    console.print()

    console.print("[bold blue]📋 Parameter Precedence[/bold blue]")
    console.print("  Priority order (highest to lowest):")
    console.print("  [cyan]1.[/cyan] CLI --param arguments")
    console.print("  [cyan]2.[/cyan] Environment variables (OSIRIS_PARAM_*)")
    console.print("  [cyan]3.[/cyan] Profile overrides")
    console.print("  [cyan]4.[/cyan] OML defaults")
    console.print()

    console.print("[bold blue]🔒 Security[/bold blue]")
    console.print("  • No secrets in compiled artifacts")
    console.print("  • Secrets must use parameter references")
    console.print("  • Compilation fails on inline secrets")
    console.print()

    console.print("[bold blue]🔄 Workflow[/bold blue]")
    console.print("  [cyan]1.[/cyan] [green]osiris compile pipeline.yaml[/green]     Compile OML to manifest")
    console.print("  [cyan]2.[/cyan] [green]osiris execute compiled/manifest.yaml[/green]  Run the pipeline")
    console.print()


def compile_command(args: list[str]):
    """Execute the compile command."""
    # Load environment variables (redundant but safe)
    loaded_envs = load_env()

    # Check for help flag or no arguments
    if not args or "--help" in args or "-h" in args:
        json_mode = "--json" in args if args else False
        show_compile_help(json_output=json_mode)
        return

    # Parse arguments manually (like run_command does)
    pipeline_file = None
    output_dir = "compiled"
    profile = None
    params = {}
    compile_mode = "auto"
    use_json = "--json" in args

    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith("--"):
            if arg == "--out":
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    output_dir = args[i + 1]
                    i += 1
                else:
                    error_msg = "Option --out requires a value"
                    if use_json:
                        print(json.dumps({"error": error_msg}))
                    else:
                        console.print(f"[red]❌ {error_msg}[/red]")
                    sys.exit(2)

            elif arg in ("--profile", "-p"):
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    profile = args[i + 1]
                    i += 1
                else:
                    error_msg = "Option --profile requires a value"
                    if use_json:
                        print(json.dumps({"error": error_msg}))
                    else:
                        console.print(f"[red]❌ {error_msg}[/red]")
                    sys.exit(2)

            elif arg == "--param":
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    param_str = args[i + 1]
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

            elif arg == "--compile":
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    mode = args[i + 1]
                    if mode in ("auto", "force", "never"):
                        compile_mode = mode
                    else:
                        error_msg = f"Invalid compile mode: {mode} (expected auto|force|never)"
                        if use_json:
                            print(json.dumps({"error": error_msg}))
                        else:
                            console.print(f"[red]❌ {error_msg}[/red]")
                        sys.exit(2)
                    i += 1

            elif arg == "--json":
                use_json = True

            elif arg == "--verbose":
                pass  # Recognized but not used

            else:
                error_msg = f"Unknown option: {arg}"
                if use_json:
                    print(json.dumps({"error": error_msg}))
                else:
                    console.print(f"[red]❌ {error_msg}[/red]")
                    console.print("[dim]💡 Run 'osiris compile --help' to see available options[/dim]")
                sys.exit(2)
        elif pipeline_file is None:
            pipeline_file = arg
        else:
            error_msg = "Multiple pipeline files specified"
            if use_json:
                print(json.dumps({"error": error_msg}))
            else:
                console.print(f"[red]❌ {error_msg}[/red]")
                console.print("[dim]💡 Only one pipeline file can be compiled at a time[/dim]")
            sys.exit(2)

        i += 1

    # Check if pipeline file was provided
    if not pipeline_file:
        error_msg = "No pipeline file specified"
        if use_json:
            print(json.dumps({"error": error_msg, "usage": "osiris compile PIPELINE_FILE"}))
        else:
            console.print(f"[red]❌ {error_msg}[/red]")
            console.print("[dim]💡 Run 'osiris compile --help' to see usage examples[/dim]")
        sys.exit(2)

    # Check if file exists
    if not Path(pipeline_file).exists():
        error_msg = f"Pipeline file not found: {pipeline_file}"
        if use_json:
            print(json.dumps({"error": error_msg}))
        else:
            console.print(f"[red]❌ {error_msg}[/red]")
        sys.exit(2)

    # Create a session for this compilation
    session_id = f"compile_{int(time.time() * 1000)}"
    session = SessionContext(session_id=session_id, base_logs_dir=Path("logs"))
    set_current_session(session)

    # Log loaded env files (masked paths)
    if loaded_envs:
        log_event("env_loaded", files=[str(p) for p in loaded_envs])

    try:
        # Log compilation start
        log_event(
            "compile_start",
            pipeline=pipeline_file,
            profile=profile,
            params=params,
            output_dir=output_dir,
        )
        start_time = time.time()

        # Compile the pipeline
        if not use_json:
            console.print(f"[cyan]🔧 Compiling {pipeline_file}...[/cyan]")
            console.print(f"[dim]📁 Session: logs/{session_id}/[/dim]")

        # Load filesystem contract
        from ..core.fs_config import load_osiris_config
        from ..core.fs_paths import FilesystemContract

        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        # Extract pipeline slug from filename
        pipeline_slug = Path(pipeline_file).stem

        # Use filesystem contract for compilation
        compiler = CompilerV0(fs_contract=fs_contract, pipeline_slug=pipeline_slug)
        success, message = compiler.compile(
            oml_path=pipeline_file, profile=profile, cli_params=params, compile_mode=compile_mode
        )

        # Calculate duration
        duration = time.time() - start_time
        log_metric("compilation_duration", duration, unit="seconds")

        if success:
            # Log successful compilation
            log_event("compile_complete", message=message, duration=duration)

            # Write to index
            from ..core.run_index import RunIndexWriter

            index_paths = fs_contract.index_paths()
            index_writer = RunIndexWriter(index_paths["base"])

            # Write latest manifest pointer
            index_writer.write_latest_manifest(
                pipeline_slug=pipeline_slug,
                profile=profile,
                manifest_hash=compiler.manifest_hash,
                manifest_path=str(
                    fs_contract.manifest_paths(
                        pipeline_slug=pipeline_slug,
                        manifest_hash=compiler.manifest_hash,
                        manifest_short=compiler.manifest_short,
                        profile=profile,
                    )["manifest"]
                ),
            )

            manifest_path = fs_contract.manifest_paths(
                pipeline_slug=pipeline_slug,
                manifest_hash=compiler.manifest_hash,
                manifest_short=compiler.manifest_short,
                profile=profile,
            )["manifest"]

            if use_json:
                print(
                    json.dumps(
                        {
                            "status": "success",
                            "message": message,
                            "session_id": session_id,
                            "manifest_path": str(manifest_path),
                            "manifest_hash": compiler.manifest_hash,
                            "manifest_short": compiler.manifest_short,
                            "pipeline_slug": pipeline_slug,
                            "profile": profile,
                        }
                    )
                )
            else:
                console.print(f"[green]✅ Compilation successful[/green]")
                console.print(f"[dim]📁 Build path: {manifest_path.parent}/[/dim]")
                console.print(f"[dim]📄 Manifest: {manifest_path}[/dim]")
                console.print(f"[dim]🔐 Hash: {compiler.manifest_short}[/dim]")
            sys.exit(0)
        else:
            # Log compilation error
            log_event("compile_error", error=message, duration=duration)

            if use_json:
                error_type = "validation_error" if "secret" in message.lower() else "compilation_error"
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "error_type": error_type,
                            "message": message,
                            "session_id": session_id,
                            "session_dir": f"logs/{session_id}",
                        }
                    )
                )
            else:
                console.print(f"[red]❌ {message}[/red]")
                console.print(f"[dim]📁 Session logs: logs/{session_id}/[/dim]")

            # Exit code 2 for validation/secret errors, 1 for internal errors
            if "secret" in message.lower() or "validation" in message.lower():
                sys.exit(2)
            else:
                sys.exit(1)
    finally:
        # Clean up session
        session.close()
        set_current_session(None)
