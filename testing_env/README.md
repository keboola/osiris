# Testing Environment

This directory is used for testing and development of Osiris pipelines. All test artifacts and generated files are isolated here to keep the main repository clean.

## Usage

Run Osiris commands from this directory to isolate all artifacts:

```bash
# From project root, use Makefile (recommended):
make chat
make init  
make validate

# Or run directly from testing_env/:
cd testing_env
python ../osiris.py chat
```

## Directory Structure

```
testing_env/
├── README.md              # This file
├── osiris.yaml            # Configuration file (auto-generated)
├── .env                   # Environment variables (create manually)
├── .osiris_sessions/      # Session data (auto-generated)
├── .osiris_cache/         # Discovery cache (auto-generated)
├── output/                # Generated pipelines and results (auto-generated)
├── *.yaml                 # Generated pipeline files (auto-generated)
└── *.csv                  # Generated data files (auto-generated)
```

## Environment Setup

1. Copy the environment template:
   ```bash
   cp ../.env.dist .env
   ```

2. Edit `.env` with your credentials:
   - Database: `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
   - Database: `SUPABASE_PROJECT_ID`, `SUPABASE_ANON_PUBLIC_KEY`
   - LLM APIs: `OPENAI_API_KEY`, `CLAUDE_API_KEY`, `GEMINI_API_KEY`

## Clean Up

To reset the testing environment:
```bash
# From project root:
rm -rf testing_env/.osiris_sessions testing_env/.osiris_cache testing_env/output
rm testing_env/*.yaml testing_env/*.csv testing_env/*.log
```

Or use git to see what's being ignored:
```bash
git status --ignored
```

All test artifacts are automatically ignored by git but the directory structure remains accessible to development tools.