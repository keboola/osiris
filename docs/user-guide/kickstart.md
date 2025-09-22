# Osiris Pipeline - Quick Start Guide

## Prerequisites

TODO: Document requirements:
- Python 3.9+ installation
- Virtual environment setup
- Required system dependencies
- Database access (MySQL/PostgreSQL/Supabase)
- API keys for LLM providers (OpenAI/Anthropic/Google)
- Optional: E2B API key for cloud execution

### System Requirements
TODO: Add minimum requirements:
- OS: Linux, macOS, Windows (WSL)
- Memory: 4GB minimum, 8GB recommended
- Disk space: 500MB for installation
- Network: Internet access for LLM APIs

## Installation

TODO: Provide step-by-step installation:

### From Source
```bash
# TODO: Add commands for:
# 1. Clone repository
# 2. Create virtual environment
# 3. Install dependencies
# 4. Verify installation
```

### Using pip (Future)
```bash
# TODO: Add pip installation when package is published
# pip install osiris-pipeline
```

### Docker (Future)
```bash
# TODO: Add Docker installation
# docker pull osiris/pipeline
```

## First Pipeline

TODO: Walk through creating first pipeline:

### Step 1: Initialize Configuration
```bash
# Create configuration files
osiris init

# TODO: Explain each file created:
# - osiris.yaml (main config)
# - osiris_connections.yaml (database connections)
# - .env (secrets)
```

### Step 2: Configure Database Connection
TODO: Show example connection setup:
```yaml
# osiris_connections.yaml example
# TODO: Add MySQL example
# TODO: Add Supabase example
# TODO: Explain connection aliases
```

### Step 3: Start Conversational Session
```bash
osiris chat

# TODO: Add example conversation:
# User: "I want to extract customer orders from MySQL..."
# Assistant: "I'll help you create a pipeline..."
```

### Step 4: Review Generated OML
TODO: Explain OML structure:
```yaml
# Example OML output
# TODO: Add annotated OML example
```

### Step 5: Compile Pipeline
```bash
osiris compile pipeline.oml

# TODO: Explain compilation output:
# - Manifest generation
# - Fingerprinting
# - Connection resolution
```

## Run & Logs

TODO: Document execution and monitoring:

### Running Locally
```bash
osiris run manifest.yaml

# TODO: Show expected output
# TODO: Explain artifacts generated
```

### Running in E2B Cloud
```bash
osiris run manifest.yaml --e2b

# TODO: Explain E2B advantages
# TODO: Show performance comparison
```

### Viewing Logs
```bash
# List all sessions
osiris logs list

# Show specific session
osiris logs show --session <id>

# Bundle for AI analysis
osiris logs bundle --session <id>

# TODO: Explain log structure:
# - events.jsonl
# - metrics.jsonl
# - artifacts/
```

### Understanding Output
TODO: Explain output structure:
- CSV files location
- Data validation
- Row counts and metrics
- Error handling

## Next Steps

TODO: Provide learning path:

### Basic Tasks
- [ ] Create a simple MySQL to CSV pipeline
- [ ] Add data transformations
- [ ] Use multiple data sources
- [ ] Schedule pipelines (when available)

### Advanced Topics
- [ ] [How-To Guide](how-to.md) - Detailed procedures
- [ ] [Crash Course](crashcourse.md) - Deep dive into concepts
- [ ] [Developer Guide](../developer-guide/components.md) - Extend Osiris
- [ ] Custom LLM prompts (Pro Mode)

### Getting Help
TODO: Add support resources:
- GitHub Issues: [link]
- Documentation: [link]
- Community Discord: [future]
- Stack Overflow tag: osiris-pipeline

## Common Issues

TODO: Add troubleshooting section:

### Connection Errors
- Database unreachable
- Invalid credentials
- Network timeouts

### LLM API Errors
- Rate limiting
- Invalid API keys
- Context length exceeded

### Compilation Errors
- Invalid OML syntax
- Missing connections
- Schema mismatches

### Runtime Errors
- Out of memory
- Data type mismatches
- File permissions

## Examples Repository

TODO: Link to examples:
- Simple pipelines
- Complex transformations
- Multi-source pipelines
- E2B cloud examples
