# Mempack Tool

A utility for creating deterministic, context-aware code packages for AI assistance.

## Overview

Mempack creates a single text file containing all relevant project files, organized with metadata and checksums. This is designed for sharing comprehensive codebase context with AI systems like ChatGPT or Claude.

## Features

- **Deterministic packing**: SHA-256 checksums for files and overall manifest
- **Configurable inclusion**: YAML-based file selection with glob patterns
- **Exclusion patterns**: Filter out unwanted files and directories
- **Project structure**: Embedded directory tree for quick navigation
- **Size limits**: Optional safety checks to prevent oversized packages
- **UTF-8 safe**: Handles text files with encoding fallback

## Usage

```bash
# Create mempack using default config
python tools/mempack/make_mempack.py

# Use custom config file
python tools/mempack/make_mempack.py --config path/to/config.yaml

# Specify different repo root
python tools/mempack/make_mempack.py --root /path/to/project
```

## Configuration

Edit `mempack.yaml` to customize what gets packed:

```yaml
# Output file location
output: ./mempack.txt

# Optional context notes
notes: |
  Brief description of current work and priorities.

# Include patterns (supports globs)
include:
  - "src/**/*.py"
  - "docs/*.md"
  - "*.toml"

# Exclude patterns (applied after include)
exclude:
  - "**/__pycache__/**"
  - "**/*.pyc"
  - "testing_env/**"

# Embed project tree structure
embed_tree: true

# Optional size limit in bytes (0 = unlimited)
max_bytes: 0
```

## Output Format

The generated mempack.txt contains:

1. **Header**: Timestamp, repo root, overall SHA-256, file count
2. **Notes**: Optional context information
3. **Project Tree**: Directory structure overview
4. **File Manifest**: JSON list with paths, checksums, and sizes
5. **File Contents**: Each file with clear delimiters and metadata

## Use Cases

- **AI Code Review**: Provide complete context for code analysis
- **Documentation**: Share project state for technical documentation
- **Debugging**: Package relevant files for troubleshooting assistance
- **Knowledge Transfer**: Comprehensive project snapshots

## File Markers

Each file in the pack uses these delimiters:
- `===== FILE BEGIN =====`
- `===== FILE END =====`

Files include path and SHA-256 hash for verification.

## Safety

- Automatic exclusion of sensitive files (git, cache, etc.)
- SHA-256 checksums detect content drift
- Size limits prevent accidental huge packages
- No secrets should be included (verify your exclude patterns)
