# Osiris Pipeline v0.1.0 - Conversational ETL Pipeline Generator

**MVP**: Basic conversational ETL pipeline generation using AI. Simple proof-of-concept implementation.

## 🚀 Quick Start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize configuration
python osiris.py init

# Start conversation
python osiris.py chat
```

## Example Conversation

```
$ python osiris.py chat

You: "Show me top 10 customers by revenue"

Bot: I'll help analyze your top customers! Let me discover your database...
     Found tables: customers, orders. I'll create a pipeline that joins these 
     and calculates total revenue per customer.

     Here's the generated pipeline:
     [Shows YAML pipeline]
     
     Does this look correct?

You: "Perfect, run it!"

Bot: ✓ Pipeline run complete! Found 10 customers, saved to output/results.csv
```

## 🎯 Pro Mode - Custom LLM Prompts

Osiris includes a powerful **pro mode** that allows advanced users to customize the AI system prompts:

```bash
# Export system prompts for customization
python osiris.py dump-prompts --export

# Edit prompts in .osiris_prompts/ directory:
# - conversation_system.txt    # Main AI personality & behavior  
# - sql_generation_system.txt  # SQL generation instructions
# - user_prompt_template.txt   # User context building template

# Use your custom prompts
python osiris.py chat --pro-mode
```

**Use Cases:**
- 🏥 **Domain-specific**: Adapt for healthcare, finance, retail terminology
- 🎨 **Response style**: Make AI more technical, concise, or detailed
- 🌍 **Multi-language**: Adapt prompts for different languages
- ⚡ **Performance**: Fine-tune for better response quality

## MVP Features

- **🤖 AI Chat Interface**: Conversational pipeline creation with natural language
- **🎯 Custom LLM Prompts**: Pro mode allows customizing AI system prompts for domain-specific use
- **🔧 Multi-Database Support**: MySQL, Supabase (PostgreSQL), and CSV file processing
- **📋 YAML Pipeline Generation**: Structured, reusable pipeline format
- **✅ Human-in-the-Loop**: Manual validation and approval before execution
- **🎨 Rich Terminal UI**: Beautiful formatted output with colors, tables, and progress indicators

**Note**: This is an early prototype. Many features are experimental.

## Supported Sources

- **MySQL/MariaDB**: Full extraction and loading support
- **Supabase**: Cloud PostgreSQL with real-time capabilities
- **CSV Files**: Local file processing

## 🚀 Running in E2B (Remote Execution)

Osiris supports remote pipeline execution in E2B sandboxes for secure, isolated runtime environments.

### Setup

1. **Get E2B API Key**: Sign up at [e2b.dev](https://e2b.dev) and get your API key
2. **Set Environment Variable**: 
   ```bash
   export E2B_API_KEY="your-api-key-here"
   ```

### Basic Usage

```bash
# Execute pipeline remotely in E2B sandbox
osiris run pipeline.yaml --e2b

# With custom resources
osiris run pipeline.yaml --e2b --e2b-cpu 4 --e2b-mem 8 --e2b-timeout 1800

# Pass environment variables to sandbox
osiris run pipeline.yaml --e2b \
  --e2b-pass-env SUPABASE_URL \
  --e2b-pass-env SUPABASE_SERVICE_ROLE_KEY

# Load env vars from file
osiris run pipeline.yaml --e2b --e2b-env-from production.env

# Dry run to see what would be sent
osiris run pipeline.yaml --e2b --dry-run
```

### E2B Options

- `--e2b`: Enable remote execution in E2B sandbox
- `--e2b-timeout SECONDS`: Execution timeout (default: 900)
- `--e2b-cpu N`: Number of CPU cores (default: 2)
- `--e2b-mem GB`: Memory in GB (default: 4)
- `--e2b-env KEY=VALUE`: Set environment variable (repeatable)
- `--e2b-env-from FILE`: Load environment variables from file
- `--e2b-pass-env NAME`: Pass environment variable from current shell (repeatable)
- `--dry-run`: Show payload details without executing

### Security Notes

- **Secrets are never written to artifacts**: Environment variables are passed securely to the sandbox at creation time
- **Allowlist-only payload**: Only essential files (manifest, runner, requirements) are uploaded
- **Isolated execution**: Each run gets a fresh sandbox with no access to local filesystem
- **Automatic cleanup**: Sandboxes are closed after execution or timeout

### Remote Artifacts

After remote execution, artifacts are downloaded to:
```
logs/<session>/remote/
├── events.jsonl      # Execution events from sandbox
├── metrics.jsonl     # Performance metrics
├── osiris.log        # Full execution log
└── artifacts/        # Output files from pipeline
```

The HTML Logs Browser automatically integrates remote execution data, showing a unified timeline of local preparation and remote execution phases.

### Testing E2B Integration

```bash
# Run unit tests (no network required)
pytest tests/e2b/

# Run live integration tests (requires E2B_API_KEY)
cd testing_env
source .env  # Contains E2B_API_KEY
export E2B_LIVE_TESTS=1
pytest tests/e2b/test_e2b_live.py
```

## Documentation

### Core Documentation
- **[CLAUDE.md](CLAUDE.md)** - AI assistant project instructions and architecture overview
- **[docs/architecture.md](docs/architecture.md)** - Technical system documentation and component relationships
- **[docs/repository-structure.md](docs/repository-structure.md)** - Complete file-by-file codebase documentation
- **[docs/pipeline-format.md](docs/pipeline-format.md)** - OML (Osiris Markup Language) specification
- **[docs/sql-safety.md](docs/sql-safety.md)** - SQL injection prevention and security measures

### Examples & Usage
- **[docs/examples/README.md](docs/examples/README.md)** - Example pipeline usage guide
- **[docs/examples/sample_pipeline.yaml](docs/examples/sample_pipeline.yaml)** - Basic MySQL pipeline template  
- **[docs/examples/top_customers_revenue.yaml](docs/examples/top_customers_revenue.yaml)** - Advanced revenue analysis pipeline

### Development Archive
- **[docs/archive/](docs/archive/)** - Historical development documentation

## License

Apache-2.0
