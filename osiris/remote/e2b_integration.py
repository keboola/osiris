"""E2B CLI integration shim for argument parsing and help text."""

from dataclasses import dataclass
import os


@dataclass
class E2BConfig:
    """E2B execution configuration."""

    enabled: bool = False
    target: str = "local"  # "local" or "e2b"
    timeout: int = 900
    cpu: int = 2
    mem_gb: int = 4
    env_vars: dict[str, str] = None
    dry_run: bool = False
    install_deps: bool = False  # Auto-install missing dependencies

    def __post_init__(self):
        if self.env_vars is None:
            self.env_vars = {}


def add_e2b_help_text(lines: list[str]) -> None:
    """Add E2B-specific help text to CLI help output.

    Args:
        lines: List to append help text lines to
    """
    lines.extend(
        [
            "",
            "[bold blue]🚀 Remote Execution (E2B)[/bold blue]",
            "  [cyan]--target[/cyan]          Execution target: local (default) or e2b",
            "  [cyan]--e2b[/cyan]             Shorthand for --target e2b",
            "  [cyan]--timeout[/cyan]         E2B sandbox timeout in seconds (default: 900)",
            "  [cyan]--cpu[/cyan]             E2B CPU cores (default: 2)",
            "  [cyan]--memory-gb[/cyan]       E2B memory in GB (default: 4)",
            "  [cyan]--e2b-env[/cyan]         Set env var in sandbox (KEY=VALUE, repeatable)",
            "  [cyan]--e2b-env-from[/cyan]    Load env vars from file",
            "  [cyan]--e2b-pass-env[/cyan]    Pass env var from current shell (repeatable)",
            "  [cyan]--e2b-install-deps[/cyan] Auto-install missing dependencies in sandbox",
            "  [cyan]--dry-run[/cyan]         Show E2B configuration without executing",
            "",
            "  [dim]Environment:[/dim]",
            "  [dim]  E2B_API_KEY      API key for E2B (required for --target e2b)[/dim]",
            "  [dim]  OSIRIS_EXECUTION_TARGET  Default execution target[/dim]",
            "  [dim]  OSIRIS_E2B_INSTALL_DEPS  Auto-install deps (1 to enable)[/dim]",
        ]
    )


def parse_e2b_args(args: list[str]) -> tuple[E2BConfig, list[str]]:
    """Parse E2B-specific arguments from command line.

    Args:
        args: Command line arguments

    Returns:
        Tuple of (E2BConfig, remaining_args)
    """
    config = E2BConfig()
    remaining = []

    # Check environment for default target
    env_target = os.environ.get("OSIRIS_EXECUTION_TARGET", "local")
    if env_target == "e2b":
        config.enabled = True
        config.target = "e2b"

    # Check environment for auto-install deps
    if os.environ.get("OSIRIS_E2B_INSTALL_DEPS") == "1":
        config.install_deps = True

    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--target":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                target = args[i + 1]
                if target == "e2b":
                    config.enabled = True
                    config.target = "e2b"
                elif target == "local":
                    config.enabled = False
                    config.target = "local"
                else:
                    # Invalid target, let it be handled by main parser
                    remaining.append(arg)
                    remaining.append(target)
                i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--e2b":
            # Shorthand for --target e2b
            config.enabled = True
            config.target = "e2b"
            i += 1

        elif arg == "--timeout":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                try:
                    config.timeout = int(args[i + 1])
                    i += 2
                except ValueError:
                    remaining.append(arg)
                    remaining.append(args[i + 1])
                    i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--cpu":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                try:
                    config.cpu = int(args[i + 1])
                    i += 2
                except ValueError:
                    remaining.append(arg)
                    remaining.append(args[i + 1])
                    i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--memory-gb":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                try:
                    config.mem_gb = int(args[i + 1])
                    i += 2
                except ValueError:
                    remaining.append(arg)
                    remaining.append(args[i + 1])
                    i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--e2b-env":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                env_str = args[i + 1]
                if "=" in env_str:
                    key, value = env_str.split("=", 1)
                    config.env_vars[key] = value
                else:
                    remaining.append(arg)
                    remaining.append(env_str)
                i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--e2b-env-from":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                env_file = args[i + 1]
                try:
                    # Load env vars from file
                    with open(env_file) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, value = line.split("=", 1)
                                config.env_vars[key.strip()] = value.strip()
                except OSError:
                    # File doesn't exist, let main parser handle error
                    remaining.append(arg)
                    remaining.append(env_file)
                i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--e2b-pass-env":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                env_key = args[i + 1]
                if env_key in os.environ:
                    config.env_vars[env_key] = os.environ[env_key]
                i += 2
            else:
                remaining.append(arg)
                i += 1

        elif arg == "--e2b-install-deps":
            config.install_deps = True
            i += 1

        elif arg == "--dry-run":
            config.dry_run = True
            i += 1

        else:
            remaining.append(arg)
            i += 1

    return config, remaining
