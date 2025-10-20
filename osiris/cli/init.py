# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Osiris project initialization command - Filesystem Contract v1 scaffolder."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from rich.console import Console

from osiris.core.config import create_sample_config

console = Console()


def init_command(args: list, json_output: bool = False) -> None:
    """Initialize a new Osiris project with Filesystem Contract v1 structure.

    Creates:
    - osiris.yaml with filesystem contract config (including MCP paths)
    - Directory structure (pipelines/, build/, aiop/, run_logs/, .osiris/)
    - .gitignore (from Appendix C)
    - .env.example and osiris_connections.example.yaml stubs
    - Optional git init + initial commit

    Filesystem Contract Config:
    - filesystem.base_path: Set to absolute path of project directory
    - filesystem.mcp_logs_dir: Set to ".osiris/mcp/logs" (relative to base_path)

    Verification:
        >>> # Verify filesystem config was written correctly
        >>> osiris init /path/to/project
        >>> yq '.filesystem.base_path' /path/to/project/osiris.yaml
        "/path/to/project"
        >>> yq '.filesystem.mcp_logs_dir' /path/to/project/osiris.yaml
        ".osiris/mcp/logs"

    Args:
        args: Command line arguments
        json_output: Whether to output JSON
    """
    # Check for help flag
    if "--help" in args or "-h" in args:
        _show_help(json_output or "--json" in args)
        return

    # Parse arguments
    parser = argparse.ArgumentParser(description="Initialize Osiris project", add_help=False)
    parser.add_argument("path", nargs="?", default=".", help="Project directory path (default: current directory)")
    parser.add_argument("--git", action="store_true", help="Initialize git repository with initial commit")
    parser.add_argument("--force", action="store_true", help="Overwrite existing osiris.yaml if present")
    parser.add_argument("--template", choices=["basic"], default="basic", help="Project template to use")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        if json_output:
            print(json.dumps({"error": "Invalid arguments"}))
        else:
            console.print("❌ Invalid arguments. Use --help for usage information.")
        sys.exit(1)

    use_json = json_output or parsed_args.json
    project_path = Path(parsed_args.path).resolve()

    try:
        # Create project directory if needed
        project_path.mkdir(parents=True, exist_ok=True)

        # Check if osiris.yaml exists
        config_file = project_path / "osiris.yaml"
        if config_file.exists() and not parsed_args.force:
            if use_json:
                print(
                    json.dumps(
                        {
                            "status": "error",
                            "message": "osiris.yaml already exists. Use --force to overwrite.",
                            "path": str(config_file),
                        }
                    )
                )
            else:
                console.print(f"❌ osiris.yaml already exists at {config_file}")
                console.print("   Use --force to overwrite.")
            sys.exit(1)

        # Create directory structure
        directories = [
            "pipelines",
            "build",
            "aiop",
            "run_logs",
            ".osiris/sessions",
            ".osiris/cache",
            ".osiris/index",
        ]

        created_dirs = []
        for dir_path in directories:
            full_path = project_path / dir_path
            if not full_path.exists():
                full_path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(dir_path)

        # Create osiris.yaml with resolved project path as base_path
        config_content = create_sample_config(to_stdout=True, base_path=str(project_path))
        config_file.write_text(config_content)

        # Create .gitignore
        gitignore_content = _get_gitignore_content()
        gitignore_file = project_path / ".gitignore"
        if not gitignore_file.exists():
            gitignore_file.write_text(gitignore_content)
            created_gitignore = True
        else:
            # Append if exists
            existing_content = gitignore_file.read_text()
            if "# Osiris Filesystem Contract v1" not in existing_content:
                gitignore_file.write_text(existing_content + "\n" + gitignore_content)
            created_gitignore = True

        # Create .env.example
        env_example_file = project_path / ".env.example"
        if not env_example_file.exists():
            env_example_content = _get_env_example_content()
            env_example_file.write_text(env_example_content)

        # Create osiris_connections.example.yaml
        connections_example_file = project_path / "osiris_connections.example.yaml"
        if not connections_example_file.exists():
            connections_example_content = _get_connections_example_content()
            connections_example_file.write_text(connections_example_content)

        # Optional git init
        git_initialized = False
        if parsed_args.git:
            git_initialized = _init_git(project_path)

        # Output results
        if use_json:
            result = {
                "status": "success",
                "message": "Osiris project initialized",
                "project_path": str(project_path),
                "created": {
                    "directories": created_dirs,
                    "osiris_yaml": True,
                    "gitignore": created_gitignore,
                    "env_example": True,
                    "connections_example": True,
                },
                "git_initialized": git_initialized,
                "next_steps": [
                    "Copy .env.example to .env and fill in credentials",
                    "Copy osiris_connections.example.yaml to osiris_connections.yaml",
                    "Run 'osiris validate' to check setup",
                    "Run 'osiris chat' to start pipeline generation",
                ],
            }
            print(json.dumps(result, indent=2))
        else:
            console.print()
            console.print("[bold green]✅ Osiris project initialized successfully![/bold green]")
            console.print()
            console.print(f"[bold]Project path:[/bold] {project_path}")
            console.print()
            console.print("[bold blue]Created:[/bold blue]")
            console.print("  ✓ osiris.yaml (Filesystem Contract v1)")
            for dir_name in created_dirs:
                console.print(f"  ✓ {dir_name}/")
            console.print("  ✓ .gitignore")
            console.print("  ✓ .env.example")
            console.print("  ✓ osiris_connections.example.yaml")
            if git_initialized:
                console.print("  ✓ Git repository initialized with initial commit")
            console.print()
            console.print("[bold blue]Next steps:[/bold blue]")
            console.print("  1. Copy .env.example to .env and fill in credentials")
            console.print("  2. Copy osiris_connections.example.yaml to osiris_connections.yaml")
            console.print("  3. Run 'osiris validate' to check setup")
            console.print("  4. Run 'osiris chat' to start pipeline generation")
            console.print()

    except Exception as e:
        if use_json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"❌ Initialization failed: {e}")
        sys.exit(1)


def _show_help(json_mode: bool) -> None:
    """Show help for init command."""
    if json_mode:
        help_data = {
            "command": "init",
            "description": "Initialize a new Osiris project with Filesystem Contract v1",
            "usage": "osiris init [PATH] [OPTIONS]",
            "arguments": {
                "PATH": "Project directory path (default: current directory)",
            },
            "options": {
                "--git": "Initialize git repository with initial commit",
                "--force": "Overwrite existing osiris.yaml if present",
                "--template": "Project template to use (default: basic)",
                "--json": "Output in JSON format",
                "--help": "Show this help message",
            },
            "creates": [
                "osiris.yaml - Filesystem Contract v1 configuration",
                "pipelines/ - Pipeline source files",
                "build/ - Deterministic compiled artifacts",
                "aiop/ - AI Observability Packs",
                "run_logs/ - Per-run logs and artifacts",
                ".osiris/ - Internal state and indexes",
                ".gitignore - Git ignore patterns",
                ".env.example - Environment variable template",
                "osiris_connections.example.yaml - Connection config template",
            ],
            "examples": ["osiris init", "osiris init /path/to/project --git", "osiris init --force --git"],
        }
        print(json.dumps(help_data, indent=2))
    else:
        console.print()
        console.print("[bold green]osiris init - Initialize Osiris Project[/bold green]")
        console.print("🚀 Create a new Osiris project with Filesystem Contract v1 structure")
        console.print()
        console.print("[bold]Usage:[/bold] osiris init [PATH] [OPTIONS]")
        console.print()
        console.print("[bold blue]Arguments[/bold blue]")
        console.print("  [cyan]PATH[/cyan]  Project directory path (default: current directory)")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--git[/cyan]       Initialize git repository with initial commit")
        console.print("  [cyan]--force[/cyan]     Overwrite existing osiris.yaml if present")
        console.print("  [cyan]--template[/cyan]  Project template to use (default: basic)")
        console.print("  [cyan]--json[/cyan]      Output in JSON format")
        console.print("  [cyan]--help[/cyan]      Show this help message")
        console.print()
        console.print("[bold blue]What this creates[/bold blue]")
        console.print("  • osiris.yaml - Filesystem Contract v1 configuration")
        console.print("  • pipelines/ - Pipeline source files")
        console.print("  • build/ - Deterministic compiled artifacts")
        console.print("  • aiop/ - AI Observability Packs")
        console.print("  • run_logs/ - Per-run logs and artifacts")
        console.print("  • .osiris/ - Internal state and indexes")
        console.print("  • .gitignore - Git ignore patterns")
        console.print("  • .env.example - Environment variable template")
        console.print("  • osiris_connections.example.yaml - Connection config template")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  osiris init")
        console.print("  osiris init /path/to/project --git")
        console.print("  osiris init --force --git")
        console.print()


def _get_gitignore_content() -> str:
    """Get .gitignore content for Filesystem Contract v1."""
    return """# Osiris Filesystem Contract v1 - Auto-generated ignore patterns

# Runtime artifacts (ephemeral, do not commit)
run_logs/
aiop/**/annex/

# Internal state (do not commit)
.osiris/cache/
.osiris/sessions/
.osiris/index/counters.sqlite
.osiris/index/counters.sqlite-shm
.osiris/index/counters.sqlite-wal

# Secrets and credentials (NEVER commit)
.env
osiris_connections.yaml

# Build artifacts (team policy - some teams commit these)
# Uncomment next line if you don't want to version build artifacts:
# build/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
ENV/
env/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Legacy logs (migration period)
logs/
"""


def _get_env_example_content() -> str:
    """Get .env.example content."""
    return """# Osiris Environment Variables Template
# Copy this file to .env and fill in your actual values

# Database Credentials
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your_username
MYSQL_PASSWORD=your_password  # pragma: allowlist secret
MYSQL_DATABASE=your_database

# Supabase
SUPABASE_PROJECT_ID=your_project_id
SUPABASE_ANON_PUBLIC_KEY=your_anon_key

# LLM API Keys
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...
GEMINI_API_KEY=...

# E2B (optional, for cloud execution)
E2B_API_KEY=...

# Filesystem Contract overrides (optional)
# OSIRIS_PROFILE=dev
# OSIRIS_FILESYSTEM_BASE=/path/to/project
# OSIRIS_RUN_ID_FORMAT=incremental,ulid
# OSIRIS_RETENTION_RUN_LOGS_DAYS=7
"""


def _get_connections_example_content() -> str:
    """Get osiris_connections.example.yaml content."""
    return """# Osiris Connections Configuration Template
# Copy this file to osiris_connections.yaml and configure your connections

version: "1.0"

connections:
  mysql:
    primary:
      default: true
      host: ${MYSQL_HOST}
      port: 3306
      user: ${MYSQL_USER}
      password: ${MYSQL_PASSWORD}
      database: ${MYSQL_DATABASE}
      pool_size: 5
      timeout: 30

  supabase:
    primary:
      default: true
      project_id: ${SUPABASE_PROJECT_ID}
      anon_key: ${SUPABASE_ANON_PUBLIC_KEY}
      service_role_key: ${SUPABASE_SERVICE_ROLE_KEY}

  duckdb:
    memory:
      default: true
      database: ":memory:"
"""


def _init_git(project_path: Path) -> bool:
    """Initialize git repository with initial commit.

    Args:
        project_path: Path to project directory

    Returns:
        True if git was initialized, False otherwise
    """
    try:
        # Check if git is available
        result = subprocess.run(["git", "--version"], capture_output=True, check=True, cwd=project_path)
        if result.returncode != 0:
            return False

        # Check if already a git repo
        git_dir = project_path / ".git"
        if git_dir.exists():
            return False

        # Initialize git
        subprocess.run(["git", "init"], capture_output=True, check=True, cwd=project_path)

        # Add files
        subprocess.run(["git", "add", "."], capture_output=True, check=True, cwd=project_path)

        # Create initial commit
        commit_message = "chore: initialize Osiris project with Filesystem Contract v1"
        subprocess.run(["git", "commit", "-m", commit_message], capture_output=True, check=True, cwd=project_path)

        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
