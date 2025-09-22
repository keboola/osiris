# Mempack Tool

A self-contained Python utility that bundles your entire codebase into a single text file for AI assistants. Perfect for getting help with debugging, code reviews, or development tasks from ChatGPT, Claude, or other LLMs.

## What is Mempack?

When working with AI assistants on coding projects, you often need to share multiple files for context. Copy-pasting files one by one is tedious and error-prone. Mempack solves this by:

1. **Collecting** all your project files based on patterns you define
2. **Running** commands to capture dynamic information (like dependency lists, database schemas)
3. **Bundling** everything into a single `.txt` file you can upload to any AI assistant
4. **Preserving** file structure and relationships so the AI understands your project

Think of it as "zip for AI" - but in a text format that AI assistants can read directly.

## Key Features

- **Zero dependencies**: Pure Python stdlib - no pip installs required
- **Smart file selection**: Include/exclude files using glob patterns (like `.gitignore`)
- **Dynamic content**: Run commands to capture real-time info (API schemas, database structures, etc.)
- **Configuration validation**: Check your config for errors before running
- **Size safety**: Set limits to avoid accidentally creating huge files
- **AI-optimized format**: Output includes file paths, commands run, and clear separators

## Quick Start

```bash
# 1. Initialize configuration (creates mempack.yaml)
python mempack.py init

# 2. Edit mempack.yaml to include your files
# (see Configuration section below)

# 3. Create your mempack
python mempack.py

# 4. Upload mempack.txt to your AI assistant
```

## Command Reference

```bash
# Initialize a new configuration file
python mempack.py init
python mempack.py init --force  # Overwrite existing config

# Validate your configuration (check for errors)
python mempack.py validate
python mempack.py validate --verbose  # Show detailed info

# Create the mempack
python mempack.py
python mempack.py --no-validate  # Skip validation (not recommended)

# Use custom config or directory
python mempack.py --config my-config.yaml
python mempack.py --root /path/to/project

# Get help
python mempack.py --help
python mempack.py validate --help
```

## Configuration

The `mempack.yaml` file controls what gets included in your pack. Here's a simple example:

### Basic Configuration

```yaml
# Where to save the output
output: ./mempack.txt

# Notes for the AI assistant (optional)
notes: |
  I'm working on a REST API bug where user authentication 
  fails intermittently. Focus on auth-related code.

# Files to include (glob patterns)
include:
  - "src/**/*.py"        # All Python files in src/
  - "tests/**/*.py"      # All test files
  - "*.md"               # All markdown files in root
  - "requirements.txt"   # Specific file

# Files to exclude (even if matched by include)
exclude:
  - "**/__pycache__/**"  # Python cache
  - "**/*.pyc"           # Compiled Python
  - ".git/**"            # Git directory
  - "venv/**"            # Virtual environment

# Include a directory tree view
embed_tree: true

# Maximum output size (6MB default)
max_bytes: 6000000
```

### Advanced: Running Commands

You can run commands to capture dynamic information:

```yaml
commands:
  # Example 1: Capture installed packages
  - output_path: env/requirements.txt
    run: pip freeze
    on_error: keep  # Continue even if command fails
    
  # Example 2: Get database schema
  - output_path: db/schema.sql
    run: |
      source .venv/bin/activate
      python manage.py dbschema --export
    timeout: 30s
    on_error: skip  # Skip this file if command fails
    
  # Example 3: List API endpoints
  - output_path: api/endpoints.json
    run: |
      source .venv/bin/activate
      python manage.py routes --json
    with_cmd: true    # Include the command in output
    on_error: fail    # Stop packing if this fails
```

#### Command Options Explained

| Option | Description | Default |
|--------|-------------|---------|
| `output_path` | Where to save command output | Required |
| `run` | Command(s) to execute | Required |
| `with_cmd` | Include command in output file | `false` |
| `timeout` | Max execution time ("30s", "2m") | `30s` |
| `on_error` | What to do if command fails:<br>• `fail`: Stop packing<br>• `keep`: Keep empty file<br>• `skip`: Omit file | `fail` |
| `shell` | Shell to use (`bash` or `sh`) | `bash` |
| `workdir` | Working directory | `.` |
| `env_pass` | Environment variables to pass (glob patterns) | `[]` |
| `capture_stderr` | Also capture error output | `false` |

## What's in the Output?

The generated `mempack.txt` is organized for easy AI consumption:

```
================================================================================
OSIRIS MEMPACK
================================================================================
GeneratedAt: 2024-01-09 10:23:45 +0100
RepoRoot: /Users/you/project
FilesCount: 42
================================================================================

NOTES:
Working on authentication bug...

PROJECT TREE:
src/
  auth/
    login.py
    tokens.py
  models/
    user.py
...

FILE MANIFEST:
[List of files with checksums]

===== FILE BEGIN =====
PATH: src/auth/login.py
SHA256: abc123...

def login(username, password):
    # Your actual code here
    ...
===== FILE END =====

===== FILE BEGIN =====
PATH: env/requirements.txt
$ pip freeze
flask==2.0.1
requests==2.26.0
...
===== FILE END =====
```

## Real-World Examples

### Example 1: Debug a Python Web App

```yaml
output: ./debug-pack.txt
notes: |
  FastAPI app crashes on user login. 
  Error: "AttributeError in auth middleware"
  
include:
  - "app/**/*.py"
  - "requirements.txt"
  - "*.env.example"
  - "docker-compose.yml"
  
exclude:
  - "**/__pycache__/**"
  - ".env"  # Never include real env files!
  
commands:
  - output_path: debug/pip-list.txt
    run: pip list
  - output_path: debug/routes.txt
    run: python -c "from app import app; print(app.routes)"
```

### Example 2: Code Review for a React Project

```yaml
output: ./review-pack.txt
notes: |
  Please review my React components for:
  - Performance optimizations
  - Best practices
  - Potential bugs
  
include:
  - "src/**/*.{js,jsx,ts,tsx}"
  - "package.json"
  - "tsconfig.json"
  - "*.md"
  
exclude:
  - "node_modules/**"
  - "build/**"
  - "coverage/**"
  
commands:
  - output_path: deps/packages.json
    run: npm list --depth=0 --json
  - output_path: deps/audit.txt
    run: npm audit
    on_error: keep  # Include even if vulnerabilities found
```

### Example 3: Document a Database Schema

```yaml
output: ./schema-pack.txt
notes: |
  Need help optimizing database queries
  
include:
  - "migrations/**/*.sql"
  - "models/**/*.py"
  - "queries/**/*.sql"
  
commands:
  - output_path: schema/tables.sql
    run: |
      mysql -u root mydb -e "SHOW TABLES"
    on_error: skip
    
  - output_path: schema/indexes.sql
    run: |
      mysql -u root mydb -e "SELECT * FROM information_schema.STATISTICS"
    on_error: skip
```

## Tips & Best Practices

1. **Security First**: Never include `.env`, `secrets`, API keys, or passwords
2. **Start Small**: Test with a few files before packing everything
3. **Use Validation**: Run `validate` before packing to catch errors
4. **Be Specific**: Use clear notes to tell the AI what you need help with
5. **Include Context**: Add README files and documentation
6. **Capture State**: Use commands to show current configuration, dependencies, etc.
7. **Size Matters**: Most AI assistants have token limits - keep packs under 10MB

## Common Issues

**Q: My pack is too large**
- Add more specific exclude patterns
- Reduce include patterns to only essential files
- Set `max_bytes` to enforce a limit

**Q: Commands aren't running**
- Check `on_error` setting - use `keep` or `skip` for optional commands
- Verify the command works in your terminal first
- Check timeout isn't too short

**Q: Validation fails**
- Run `python mempack.py validate --verbose` to see details
- Common issues: typos in YAML, missing required fields, invalid values

## License

This tool is provided as-is for use with AI assistance tools. No warranty implied.
