#!/usr/bin/env python3
"""
mempack.py - A self-contained Python tool to pack multiple files into a single text file.
Supports command execution to generate dynamic content before packing.
No external dependencies - stdlib only.
"""
import argparse
from fnmatch import fnmatch, fnmatchcase
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess  # nosec B404
import sys
import time
from typing import Any

BANNER = "=" * 80
FILE_BEGIN = "===== FILE BEGIN ====="
FILE_END = "===== FILE END ====="

DEFAULT_MEMPACK_YAML = """# Output file (you will upload this single file to ChatGPT)
output: ./mempack.txt

notes: |
  Your project description

include:
# Core src
- main.py
- pyproject.toml
- requirements.txt

# Docs
- docs*

# Tests (unit+integration+chat)
- tests/**/**/*.py

# Repo meta (helps reviewers)
- CHANGELOG.md
- CLAUDE.md
- SECURITY.md
- LICENSE
- Makefile
- README.md

exclude:
# Python noise
- "**/__pycache__/**"
- "**/*.pyc"

# Runtime outputs / logs / artifacts (huge & non-deterministic)
- logs/**
- output/**
- tmp/**
- "**/artifacts/**"
- "**/events.jsonl"
- "**/metrics.jsonl"
- "**/*.log"

# Repo internals
- .git/**
- osiris_pipeline.egg-info/**
- uv.lock

# Also embed a fresh project tree (so I can see structure at-a-glance)
embed_tree: true

# Automatically exclude files/dirs from .gitignore
# When true, patterns from .gitignore are applied before explicit excludes
# Include patterns can override gitignore/exclude patterns (include wins)
use_gitignore: true

# Safety: cap the size so we don't over-feed the model by accident
max_bytes: 6000000 # ~6 MB, tweak if needed

# ----------------------------------------------------------
# Commands: run before packing and include their stdout files
# ----------------------------------------------------------
commands:
  - output_path: tools/mempack/gen/components.json
    # What to run (multi-line allowed). 'bash -lc' is used so 'source' works.
    run: |
      source .venv/bin/activate
      python main.py --help
    # Store the exact command text next to output (file+".cmd.txt")
    with_cmd: true
    # Shell to use; default: bash
    shell: bash
    # Timeout; supports "30s", "2m" or integer seconds
    timeout: 30s
    # Working directory; default: "."
    workdir: .
    # Allow-list of environment variables (glob patterns); default: []
    env_pass:
      - HELP_*
    # Error handling strategy:
    # - fail: abort packing if exit code != 0
    # - keep: keep stdout file (may be empty), log error to console, continue
    # - skip: do not write output file, log error to console, continue
    on_error: fail
    # Do not store stderr unless explicitly requested
    capture_stderr: false
"""


def sha256_bytes(data: bytes) -> str:
    """Calculate SHA256 hash of bytes."""
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def parse_gitignore(gitignore_path: Path) -> list[str]:
    """
    Parse .gitignore file and return list of patterns.
    Handles comments, blank lines, and basic gitignore syntax.
    """
    if not gitignore_path.exists():
        return []

    patterns = []
    with open(gitignore_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            patterns.append(line)

    return patterns


def matches_gitignore_pattern(path: Path, pattern: str, root: Path) -> bool:
    """
    Check if a path matches a gitignore pattern.
    Handles directory patterns (ending with /), negation (!), and wildcards.
    """
    # Get relative path from root
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        return False

    # Convert to posix for consistent matching
    rel_str = rel_path.as_posix()

    # Handle negation (we'll deal with this at a higher level)
    if pattern.startswith("!"):
        return False

    # Remove leading slash if present
    if pattern.startswith("/"):
        pattern = pattern[1:]
        # Pattern with leading slash only matches from root
        return fnmatch(rel_str, pattern) or (path.is_dir() and fnmatch(rel_str + "/", pattern))

    # Directory-only pattern (ends with /)
    if pattern.endswith("/"):
        if not path.is_dir():
            return False
        pattern = pattern[:-1]

    # Check if pattern matches the path or any parent component
    # This handles patterns like "__pycache__" matching "src/__pycache__/file.pyc"
    parts = rel_str.split("/")
    for i in range(len(parts)):
        partial = "/".join(parts[i:])
        if fnmatch(partial, pattern):
            return True
        # Also check against individual directory names
        if fnmatch(parts[i], pattern) and (path.is_dir() or i < len(parts) - 1):
            # It's a directory in the path
            return True

    return False


def parse_yaml_simple(text: str) -> dict[str, Any]:
    """
    Simple YAML parser for our specific needs.
    Handles strings, lists, booleans, numbers, and multiline strings with |.
    Special handling for commands section with list of dicts.
    """
    lines = text.split("\n")
    result = {}
    current_key = None
    current_list = None
    in_multiline = False
    multiline_buffer = []
    in_commands = False
    current_command = None
    command_indent = 0
    indent_level = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            if in_multiline and line and not line.strip().startswith("#"):
                # Include empty lines in multiline strings
                multiline_buffer.append("")
            i += 1
            continue

        # Calculate indentation
        spaces = len(line) - len(line.lstrip())

        # Handle multiline strings
        if in_multiline:
            if spaces >= indent_level:
                multiline_buffer.append(line[indent_level:])
            else:
                # End of multiline
                if in_commands and current_command:
                    current_command[current_key] = "\n".join(multiline_buffer)
                else:
                    result[current_key] = "\n".join(multiline_buffer)
                in_multiline = False
                multiline_buffer = []
                continue  # Reprocess this line
            i += 1
            continue

        # Handle commands section
        if in_commands:
            # Check if we're still in commands section
            if spaces == 0 and ":" in line and not line.startswith("-"):
                # New top-level key, exit commands mode
                in_commands = False
                current_command = None
                continue  # Reprocess this line

            # Handle command list items
            if stripped.startswith("- ") and (spaces in {0, 2}):
                # Save previous command if exists
                if current_command:
                    if "commands" not in result:
                        result["commands"] = []
                    result["commands"].append(current_command)

                # Start new command
                current_command = {}
                command_indent = spaces

                # Check if there's an inline key-value
                value = stripped[2:].strip()
                if ":" in value:
                    key, val = value.split(":", 1)
                    current_command[key.strip()] = val.strip()

                i += 1
                continue

            # Handle command properties
            if current_command is not None and ":" in line and spaces > command_indent:
                key, value = line.strip().split(":", 1)
                key = key.strip()
                value = value.strip()
                current_key = key

                if value == "|":
                    # Start multiline string for command
                    in_multiline = True
                    # Find actual indent on next non-empty line
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j]
                        if next_line.strip() and not next_line.strip().startswith("#"):
                            indent_level = len(next_line) - len(next_line.lstrip())
                            break
                        j += 1
                elif value in {"", "[]"} or value.startswith("#"):
                    # Start a list for command property (handle inline comments)
                    current_command[key] = []
                    # Read list items
                    j = i + 1
                    while j < len(lines):
                        list_line = lines[j]
                        list_stripped = list_line.strip()
                        if list_stripped.startswith("- "):
                            list_value = list_stripped[2:].strip()
                            if list_value.startswith('"') and list_value.endswith('"'):
                                list_value = list_value[1:-1]
                            current_command[key].append(list_value)
                            j += 1
                        elif not list_stripped or list_stripped.startswith("#"):
                            j += 1
                        else:
                            break
                    i = j - 1
                else:
                    # Parse value - handle inline comments
                    if "#" in value:
                        value = value.split("#")[0].strip()

                    if value.lower() in ("true", "yes"):
                        current_command[key] = True
                    elif value.lower() in ("false", "no"):
                        current_command[key] = False
                    elif value.isdigit():
                        current_command[key] = int(value)
                    elif value.endswith("s") or value.endswith("m"):
                        current_command[key] = value
                    else:
                        current_command[key] = value

                i += 1
                continue

        # Handle list items
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"') or value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            if current_list is not None:
                current_list.append(value)
            i += 1
            continue

        # Handle key-value pairs
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # End any current list
            if current_list is not None and current_key:
                result[current_key] = current_list
                current_list = None

            # Save any pending command
            if in_commands and current_command:
                if "commands" not in result:
                    result["commands"] = []
                result["commands"].append(current_command)
                current_command = None
                in_commands = False

            current_key = key

            if key == "commands":
                # Enter commands mode
                in_commands = True
                result["commands"] = []
            elif value == "|":
                # Start multiline string
                in_multiline = True
                # Find actual indent on next non-empty line
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    if next_line.strip() and not next_line.strip().startswith("#"):
                        indent_level = len(next_line) - len(next_line.lstrip())
                        break
                    j += 1
            elif value in {"", "[]"}:
                # Start a list
                current_list = []
            else:
                # Simple value
                if value.lower() in ("true", "yes"):
                    result[key] = True
                elif value.lower() in ("false", "no"):
                    result[key] = False
                elif value.isdigit():
                    result[key] = int(value)
                elif value.startswith('"') and value.endswith('"') or value.startswith("'") and value.endswith("'"):
                    result[key] = value[1:-1]
                else:
                    # Handle inline comments
                    if "#" in value:
                        value = value.split("#")[0].strip()
                    # Try to parse as number
                    try:
                        if "." in value:
                            result[key] = float(value)
                        else:
                            result[key] = int(value)
                    except ValueError:
                        result[key] = value
                current_key = None

        i += 1

    # Finalize any pending items
    if current_list is not None and current_key:
        result[current_key] = current_list

    if in_commands and current_command:
        if "commands" not in result:
            result["commands"] = []
        result["commands"].append(current_command)

    return result


def iter_paths(
    root: Path, patterns: list[str], excludes: list[str], use_gitignore: bool = False
) -> tuple[list[Path], list[str]]:
    """Expand include globs relative to repo root, filter with excludes, sort.
    Returns (list_of_paths, list_of_collision_warnings).
    """
    collisions = []

    # Step 1: Collect all included files
    included_paths: set[Path] = set()
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file():
                included_paths.add(p.resolve())

    # Step 2: Apply gitignore patterns if enabled
    gitignored: set[Path] = set()
    if use_gitignore:
        gitignore_path = root / ".gitignore"
        gitignore_patterns = parse_gitignore(gitignore_path)

        # Check all included paths against gitignore
        for p in list(included_paths):
            for pattern in gitignore_patterns:
                if pattern.startswith("!"):
                    # Negation pattern - skip for now (could be enhanced)
                    continue
                if matches_gitignore_pattern(p, pattern, root):
                    gitignored.add(p)
                    break

    # Step 3: Apply explicit excludes
    explicitly_excluded: set[Path] = set()
    for pat in excludes:
        for p in root.glob(pat):
            if p.exists():
                explicitly_excluded.add(p.resolve())
                if p.is_dir():
                    for sub in p.rglob("*"):
                        explicitly_excluded.add(sub.resolve())

    # Step 4: Calculate what would be excluded
    would_be_excluded = gitignored.union(explicitly_excluded)

    # Step 5: Check for collisions (included files that would be excluded)
    for p in included_paths:
        if p in would_be_excluded:
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                rel = str(p)

            if p in gitignored:
                collisions.append(f"Including '{rel}' (overrides .gitignore)")
            elif p in explicitly_excluded:
                collisions.append(f"Including '{rel}' (overrides exclude pattern)")

    # Step 6: Include patterns win - keep all included paths
    final = sorted(included_paths)

    return final, collisions


def build_tree(root: Path, use_gitignore: bool = False, excludes: list[str] = None) -> str:
    """Compact tree without external deps; directories first, then files (sorted).
    Respects gitignore patterns if enabled.
    """
    if excludes is None:
        excludes = []

    # Load gitignore patterns if enabled
    gitignore_patterns = []
    if use_gitignore:
        gitignore_path = root / ".gitignore"
        gitignore_patterns = parse_gitignore(gitignore_path)

    lines = []
    for base, dirs, files in os.walk(root):
        base_path = Path(base)

        # Skip if current directory should be excluded
        skip_dir = False

        # Check gitignore patterns
        if use_gitignore:
            for pattern in gitignore_patterns:
                if pattern.startswith("!"):
                    continue
                if matches_gitignore_pattern(base_path, pattern, root):
                    skip_dir = True
                    break

        # Check explicit excludes
        if not skip_dir:
            for pat in excludes:
                try:
                    # Handle both glob patterns and simple names
                    if base_path.match(pat) or base_path.name == pat:
                        skip_dir = True
                        break
                except Exception:  # nosec B110
                    pass

        if skip_dir:
            dirs[:] = []  # Don't recurse into this directory
            continue

        rel = os.path.relpath(base, root)
        if rel == ".":
            rel = ""
        if rel:
            lines.append(rel + "/")

        # Filter and sort directories
        filtered_dirs = []
        for d in sorted(dirs):
            if d.startswith("."):
                continue

            dir_path = base_path / d
            skip = False

            # Check gitignore
            if use_gitignore:
                for pattern in gitignore_patterns:
                    if pattern.startswith("!"):
                        continue
                    if matches_gitignore_pattern(dir_path, pattern, root):
                        skip = True
                        break

            # Check explicit excludes
            if not skip:
                for pat in excludes:
                    try:
                        if dir_path.match(pat) or d == pat:
                            skip = True
                            break
                    except Exception:  # nosec B110
                        pass

            if not skip:
                filtered_dirs.append(d)
                lines.append(os.path.join(rel, d) + "/")

        dirs[:] = filtered_dirs  # Update dirs list for os.walk recursion

        # Filter and add files
        for f in sorted(files):
            file_path = base_path / f
            skip = False

            # Check gitignore
            if use_gitignore:
                for pattern in gitignore_patterns:
                    if pattern.startswith("!"):
                        continue
                    if matches_gitignore_pattern(file_path, pattern, root):
                        skip = True
                        break

            # Check explicit excludes
            if not skip:
                for pat in excludes:
                    try:
                        if file_path.match(pat) or f == pat:
                            skip = True
                            break
                    except Exception:  # nosec B110
                        pass

            if not skip:
                lines.append(os.path.join(rel, f))

    return "\n".join(lines)


def parse_timeout(timeout_str: str) -> int:
    """Parse timeout string to seconds. Supports '30s', '2m', or integer seconds."""
    if isinstance(timeout_str, int):
        return timeout_str

    timeout_str = str(timeout_str).strip()
    if timeout_str.endswith("s"):
        return int(timeout_str[:-1])
    elif timeout_str.endswith("m"):
        return int(timeout_str[:-1]) * 60
    else:
        return int(timeout_str)


def _run_command_item(item: dict[str, Any]) -> list[str]:
    """
    Executes a single command item (see schema).
    Returns the list of produced file paths for inclusion in the pack.
    """
    output_path = Path(item["output_path"])
    run_cmd = item["run"].strip()
    with_cmd = item.get("with_cmd", False)
    shell = item.get("shell", "bash")
    timeout = parse_timeout(item.get("timeout", "30s"))
    workdir = item.get("workdir", ".")
    env_pass = item.get("env_pass", [])
    on_error = item.get("on_error", "fail")
    capture_stderr = item.get("capture_stderr", False)

    # Build clean environment with allowlist
    clean_env = {}
    for pattern in env_pass:
        for key, value in os.environ.items():
            if fnmatchcase(key, pattern):
                clean_env[key] = value

    # Add PATH for basic commands
    if "PATH" not in clean_env:
        clean_env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")

    # Prepare shell command
    shell_cmd = ["bash", "-lc", run_cmd] if shell == "bash" else ["sh", "-lc", run_cmd]

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run command
    try:
        result = subprocess.run(  # nosec B603
            shell_cmd, check=False, cwd=workdir, env=clean_env, capture_output=True, text=True, timeout=timeout
        )

        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr

        # Get first line of command for summary
        first_line = run_cmd.split("\n")[0][:50]
        if len(run_cmd.split("\n")[0]) > 50:
            first_line += "..."

        if exit_code == 0:
            print(f"[mempack] OK  EXIT={exit_code} → {first_line}")
        else:
            print(f"[mempack] ERR EXIT={exit_code} → {first_line}")
            if stderr:
                print(f"STDERR:\n{stderr}", file=sys.stderr)

            if on_error == "fail":
                # Clean up any partial outputs and abort
                if output_path.exists():
                    output_path.unlink()
                raise SystemExit(exit_code)
            elif on_error == "skip":
                # Don't write anything, continue
                return []

        # Write outputs
        produced_files = []

        # Create a formatted output that shows command execution context
        if with_cmd:
            # Convert multiline command to single line with semicolons for clarity
            formatted_cmd = run_cmd.replace("\n", "; ")
            # Add shell prompt-like format
            formatted_output = f"$ {formatted_cmd}\n{stdout}"
            output_path.write_text(formatted_output, encoding="utf-8")
        else:
            # Just write the raw output
            output_path.write_text(stdout, encoding="utf-8")

        produced_files.append(str(output_path))

        # Optionally capture stderr
        if capture_stderr and stderr:
            stderr_path = Path(str(output_path) + ".stderr.txt")
            stderr_path.write_text(stderr, encoding="utf-8")
            produced_files.append(str(stderr_path))

        return produced_files

    except subprocess.TimeoutExpired:
        print(f"[mempack] ERR TIMEOUT → {first_line}")
        if on_error == "fail":
            raise SystemExit(1) from None
        elif on_error == "skip":
            return []
        else:  # keep
            # Write empty file
            output_path.write_text("", encoding="utf-8")
            return [str(output_path)]


def generate_command_outputs_and_collect(mempack_yaml_path: str = "mempack.yaml") -> list[str]:
    """
    Executes all `commands` from mempack.yaml, writes outputs to disk,
    logs to console (including EXIT=<code>), and returns a list of produced file paths
    (stdout file, optional .cmd.txt, optional .stderr.txt).
    Raises SystemExit on `on_error: fail` with the command's exit code.
    """
    yaml_path = Path(mempack_yaml_path)
    if not yaml_path.exists():
        return []

    config = parse_yaml_simple(yaml_path.read_text(encoding="utf-8"))
    commands = config.get("commands", [])

    if not commands:
        return []

    print(f"[mempack] Found {len(commands)} command(s) to execute")
    all_files = []
    for idx, item in enumerate(commands, 1):
        if "output_path" not in item or "run" not in item:
            print(f"[mempack] SKIP command {idx}: invalid (missing output_path or run)")
            continue

        print(f"[mempack] Executing command {idx}/{len(commands)}: {item['output_path']}")
        files = _run_command_item(item)
        all_files.extend(files)

    return all_files


def cmd_init(args):
    """Initialize a new mempack.yaml file."""
    yaml_path = Path("mempack.yaml")

    if yaml_path.exists() and not args.force:
        print("[ERROR] mempack.yaml already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    yaml_path.write_text(DEFAULT_MEMPACK_YAML, encoding="utf-8")
    print("[OK] Created mempack.yaml")


def validate_config(config_path: str, print_output: bool = True) -> tuple[bool, list[str], list[str], dict]:
    """
    Validate mempack.yaml configuration.
    Returns (is_valid, list_of_errors, list_of_warnings, config_dict).
    """
    errors = []
    warnings = []

    yaml_path = Path(config_path)
    if not yaml_path.exists():
        return False, [f"Config file not found: {config_path}"], [], {}

    try:
        cfg = parse_yaml_simple(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"Failed to parse YAML: {e}"], [], {}

    # Validate output path
    if "output" not in cfg:
        warnings.append("No 'output' specified, will use default './mempack.txt'")

    # Validate include patterns
    if "include" not in cfg or not cfg.get("include"):
        warnings.append("No 'include' patterns specified, no files will be packed")
    elif not isinstance(cfg.get("include"), list):
        errors.append("'include' must be a list of patterns")

    # Validate exclude patterns
    if "exclude" in cfg and not isinstance(cfg.get("exclude"), list):
        errors.append("'exclude' must be a list of patterns")

    # Validate use_gitignore
    if "use_gitignore" in cfg:
        if not isinstance(cfg["use_gitignore"], bool):
            warnings.append(f"'use_gitignore' should be boolean, got: {cfg['use_gitignore']}")
        elif cfg["use_gitignore"]:
            gitignore_path = Path(".gitignore")
            if not gitignore_path.exists():
                warnings.append("'use_gitignore' is true but .gitignore file not found")

    # Validate max_bytes
    if "max_bytes" in cfg:
        try:
            mb = int(cfg["max_bytes"])
            if mb < 0:
                errors.append("'max_bytes' must be non-negative")
        except (ValueError, TypeError):
            errors.append(f"'max_bytes' must be an integer, got: {cfg['max_bytes']}")

    # Validate commands
    if "commands" in cfg:
        if not isinstance(cfg["commands"], list):
            errors.append("'commands' must be a list")
        else:
            for idx, cmd in enumerate(cfg["commands"], 1):
                if not isinstance(cmd, dict):
                    errors.append(f"Command {idx}: must be a dictionary")
                    continue

                # Required fields
                if "output_path" not in cmd:
                    errors.append(f"Command {idx}: missing required 'output_path'")
                if "run" not in cmd:
                    errors.append(f"Command {idx}: missing required 'run' command")
                elif not cmd["run"].strip():
                    errors.append(f"Command {idx}: 'run' command is empty")

                # Validate on_error
                if "on_error" in cmd and cmd["on_error"] not in ["fail", "keep", "skip"]:
                    errors.append(f"Command {idx}: 'on_error' must be 'fail', 'keep', or 'skip'")

                # Validate timeout
                if "timeout" in cmd:
                    try:
                        parse_timeout(cmd["timeout"])
                    except (ValueError, TypeError):
                        errors.append(f"Command {idx}: invalid timeout format '{cmd['timeout']}'")

                # Validate shell
                if "shell" in cmd and cmd["shell"] not in ["bash", "sh"]:
                    warnings.append(f"Command {idx}: unusual shell '{cmd['shell']}', expected 'bash' or 'sh'")

                # Validate boolean fields
                for bool_field in ["with_cmd", "capture_stderr"]:
                    if bool_field in cmd and not isinstance(cmd[bool_field], bool):
                        warnings.append(f"Command {idx}: '{bool_field}' should be boolean")

    # Print output if requested
    if print_output:
        if warnings:
            print("[mempack] Validation warnings:")
            for w in warnings:
                print(f"  ⚠ {w}")

        if errors:
            print("[mempack] Validation errors:", file=sys.stderr)
            for e in errors:
                print(f"  ✗ {e}", file=sys.stderr)

    return len(errors) == 0, errors, warnings, cfg


def cmd_validate(args):
    """Validate mempack.yaml configuration."""
    print(f"[mempack] Validating {args.config}")

    # Don't print errors/warnings here - we'll do it after
    is_valid, errors, warnings, cfg = validate_config(args.config, print_output=False)

    # Always show errors and warnings first
    if warnings:
        print("\n[mempack] Validation warnings:")
        for w in warnings:
            print(f"  ⚠ {w}")

    if errors:
        print("\n[mempack] Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)

    if is_valid:
        print("\n[mempack] ✓ Configuration is valid")

        # Optionally show what would be done
        if args.verbose and cfg:
            print("\n[mempack] Configuration summary:")
            print(f"  Output: {cfg.get('output', './mempack.txt')}")
            print(f"  Include patterns: {len(cfg.get('include', []))}")
            print(f"  Exclude patterns: {len(cfg.get('exclude', []))}")
            print(f"  Embed tree: {cfg.get('embed_tree', True)}")
            print(f"  Use .gitignore: {cfg.get('use_gitignore', False)}")

            if "max_bytes" in cfg:
                try:
                    mb = int(cfg["max_bytes"]) / (1024 * 1024)
                    print(f"  Max size: {mb:.1f} MB")
                except (ValueError, TypeError):
                    print(f"  Max size: invalid ({cfg['max_bytes']})")

            if "commands" in cfg:
                print(f"  Commands to run: {len(cfg['commands'])}")
                for idx, cmd in enumerate(cfg["commands"], 1):
                    if isinstance(cmd, dict):
                        cmd_preview = cmd.get("run", "")
                        if isinstance(cmd_preview, str):
                            # Take first line or first 50 chars
                            first_line = cmd_preview.split("\n")[0] if cmd_preview else ""
                            if len(first_line) > 50:
                                first_line = first_line[:50] + "..."
                            print(f"    {idx}. {cmd.get('output_path', 'unknown')} ← {first_line}")

        return 0
    else:
        print(f"\n[mempack] ✗ Configuration has {len(errors)} error(s)", file=sys.stderr)
        # Still show verbose info even with errors
        if args.verbose and cfg:
            print("\n[mempack] Partial configuration info:", file=sys.stderr)
            print(f"  Config file: {args.config}", file=sys.stderr)
            if "commands" in cfg:
                print(f"  Commands defined: {len(cfg.get('commands', []))}", file=sys.stderr)
            if "include" in cfg:
                print(f"  Include patterns: {len(cfg.get('include', []))}", file=sys.stderr)
        return 1


def cmd_pack(args):
    """Main packing command."""
    root = Path(args.root).resolve()
    yaml_path = Path(args.config)

    if not yaml_path.exists():
        print(f"[ERROR] Config file not found: {yaml_path}", file=sys.stderr)
        print("Run 'mempack.py init' to create a starter mempack.yaml", file=sys.stderr)
        sys.exit(1)

    # Validate configuration first if not skipping
    if not args.no_validate:
        is_valid, errors, warnings, _ = validate_config(args.config)
        if not is_valid:
            print(
                f"[ERROR] Configuration validation failed with {len(errors)} error(s)",
                file=sys.stderr,
            )
            print("Use --no-validate to skip validation (not recommended)", file=sys.stderr)
            sys.exit(1)

    cfg = parse_yaml_simple(yaml_path.read_text(encoding="utf-8"))

    out_path = Path(cfg.get("output", "./mempack.txt")).resolve()
    include = cfg.get("include", [])
    exclude = cfg.get("exclude", [])
    embed_tree = bool(cfg.get("embed_tree", True))
    use_gitignore = bool(cfg.get("use_gitignore", False))
    notes = cfg.get("notes", "").strip()
    max_bytes = int(cfg.get("max_bytes", 0))

    # Run commands first and collect generated files
    print("[mempack] Running commands...")
    generated_files = generate_command_outputs_and_collect(args.config)

    # Collect files from include/exclude
    print("[mempack] Collecting files...")
    if use_gitignore:
        print("[mempack] Using .gitignore patterns")

    files, collisions = iter_paths(root, include, exclude, use_gitignore)

    # Show collision warnings
    if collisions:
        print("[mempack] Include/exclude collisions detected:")
        for warning in collisions[:10]:  # Show first 10 warnings
            print(f"  ⚠ {warning}")
        if len(collisions) > 10:
            print(f"  ... and {len(collisions) - 10} more")

    # Add generated files (bypass filters)
    for gen_file in generated_files:
        gen_path = Path(gen_file).resolve()
        if gen_path.exists() and gen_path not in files:
            files.append(gen_path)

    # Sort all files
    files.sort()

    # Collect file chunks deterministically
    chunks = []
    file_digests = []
    total_bytes = 0

    for p in files:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            # File is outside root (e.g., generated file with absolute path)
            rel = str(p)

        data = p.read_bytes()
        digest = sha256_bytes(data)
        file_digests.append({"path": rel, "sha256": digest, "bytes": len(data)})

        header = f"{FILE_BEGIN}\nPATH: {rel}\nSHA256: {digest}\n"
        footer = f"{FILE_END}\n"
        try:
            text_content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text_content = "[Binary or unreadable file]"

        chunk = header + "\n" + text_content + "\n" + footer
        total_bytes += len(chunk.encode("utf-8"))
        chunks.append(chunk)

    # Overall digest to detect pack drift
    manifest_json = json.dumps(file_digests, sort_keys=True).encode("utf-8")
    overall_digest = sha256_bytes(manifest_json)

    # Compose output
    buf = io.StringIO()
    buf.write(f"{BANNER}\nOSIRIS MEMPACK\n{BANNER}\n")
    buf.write(f"GeneratedAt: {time.strftime('%Y-%m-%d %H:%M:%S %z')}\n")
    buf.write(f"RepoRoot: {root}\n")
    buf.write(f"OverallSHA256: {overall_digest}\n")
    buf.write(f"FilesCount: {len(files)}\n")
    if use_gitignore:
        buf.write("GitignoreApplied: true\n")
    if collisions:
        buf.write(f"IncludeOverrides: {len(collisions)}\n")
    buf.write(f"{BANNER}\n\n")

    if notes:
        buf.write("NOTES:\n")
        buf.write(notes + "\n\n" + BANNER + "\n\n")

    if embed_tree:
        buf.write("PROJECT TREE (relative paths):\n")
        buf.write(BANNER + "\n")
        buf.write(build_tree(root, use_gitignore, exclude) + "\n")
        buf.write(BANNER + "\n\n")

    buf.write("FILE MANIFEST:\n")
    buf.write(json.dumps(file_digests, indent=2, sort_keys=True))
    buf.write("\n\n" + BANNER + "\n\n")

    for chunk in chunks:
        buf.write(chunk)
        buf.write("\n")

    out_bytes = buf.getvalue().encode("utf-8")
    if max_bytes and len(out_bytes) > max_bytes:
        print(
            f"[ERROR] mempack would be {len(out_bytes)} bytes, exceeds max_bytes={max_bytes}",
            file=sys.stderr,
        )
        sys.exit(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    # Summary output
    summary_parts = [f"{len(files)} files"]
    if use_gitignore:
        summary_parts.append(".gitignore applied")
    if collisions:
        summary_parts.append(f"{len(collisions)} overrides")

    print(f"[OK] Wrote {out_path} ({len(out_bytes)} bytes)")
    print(f"[OK] Packed: {', '.join(summary_parts)}")
    print(f"[OK] OverallSHA256 = {overall_digest}")


def main():
    """Main entry point with subcommand support."""
    parser = argparse.ArgumentParser(
        prog="mempack.py",
        description="Pack multiple files into a single text file for AI consumption.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
USAGE:
  %(prog)s              # Pack files according to mempack.yaml
  %(prog)s init         # Create a starter mempack.yaml
  %(prog)s validate     # Validate mempack.yaml configuration
  %(prog)s --help       # Show this help

DESCRIPTION:
  mempack bundles your project files into a single text file that can be
  uploaded to AI assistants like ChatGPT or Claude. It supports:

  - Selective file inclusion/exclusion via glob patterns
  - Dynamic content generation via shell commands
  - SHA256 checksums for integrity verification
  - File size limits to prevent oversized outputs
  - Project tree visualization
  - Configuration validation

EXAMPLES:
  # Initialize a new mempack.yaml configuration
  python mempack.py init

  # Validate configuration before packing
  python mempack.py validate
  python mempack.py validate --verbose

  # Pack files (runs commands first, then builds the pack)
  python mempack.py

  # Pack without validation (not recommended)
  python mempack.py --no-validate

  # Use a custom config file
  python mempack.py --config my-config.yaml

  # Pack from a different root directory
  python mempack.py --root /path/to/project
""",
    )

    # Create subparsers - use parents to inherit common arguments
    # Create a parent parser for common arguments
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--config",
        "-c",
        default="mempack.yaml",
        help="Path to mempack.yaml configuration file (default: mempack.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init subcommand
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new mempack.yaml configuration file",
        description="Creates a starter mempack.yaml file with sensible defaults for Python projects.",
    )
    init_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing mempack.yaml if it exists")

    # Validate subcommand - inherits --config from parent
    validate_parser = subparsers.add_parser(
        "validate",
        parents=[parent_parser],
        help="Validate mempack.yaml configuration",
        description="Checks the configuration file for errors and warnings before packing.",
    )
    validate_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed configuration summary")

    # Add arguments for main pack command (when no subcommand is given)
    parser.add_argument(
        "--config",
        "-c",
        default="mempack.yaml",
        help="Path to mempack.yaml configuration file (default: mempack.yaml)",
    )
    parser.add_argument(
        "--root",
        "-r",
        default=".",
        help="Root directory for file resolution (default: current directory)",
    )
    parser.add_argument("--no-validate", action="store_true", help="Skip configuration validation (not recommended)")

    args = parser.parse_args()

    # Route to appropriate command
    if args.command == "init":
        cmd_init(args)
    elif args.command == "validate":
        sys.exit(cmd_validate(args))
    else:
        # Default to pack command
        cmd_pack(args)


if __name__ == "__main__":
    main()
