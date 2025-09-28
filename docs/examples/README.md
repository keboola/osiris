# Osiris Examples

Example pipeline files and AI Operation Package (AIOP) exports demonstrating Osiris capabilities.

## Pipeline Examples (OML Format)

- **`mysql_to_local_csv_all_tables.yaml`** - MySQL to CSV export pipeline
- **`mysql_to_supabase_all_tables.yaml`** - MySQL to Supabase migration pipeline
- **`mysql_duckdb_supabase_demo.yaml`** - MySQL → DuckDB → Supabase transformation pipeline (NEW)

## AIOP Examples

- **`aiop-sample.json`** - Complete AI Operation Package with all layers
- **`run-card-sample.md`** - Human-readable run summary in Markdown

## Usage

### Pipeline Examples

These files show the OML v0.1.0 format. To generate your own pipelines:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Initialize configuration
python osiris.py init

# Generate pipeline through conversation
python osiris.py chat

# Run example pipeline with dry-run
python osiris.py run examples/mysql_to_local_csv_all_tables.yaml --dry-run
```

### MySQL → DuckDB → Supabase Demo

The `mysql_duckdb_supabase_demo.yaml` demonstrates data transformation using DuckDB:

**Purpose**: Extract movie data from MySQL, compute director statistics using DuckDB SQL, and write results to Supabase.

**Quick Start**:
```bash
# Using make target (recommended)
make demo-mysql-duckdb-supabase

# Or manually from testing_env
cd testing_env
python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml
python ../osiris.py run --last-compile
```

**Expected Output**:
- Extracts ~14 movies from MySQL
- Computes statistics per director (movie count, avg runtime, total box office, ROI)
- Creates/updates `director_stats_demo` table in Supabase with aggregated results

**Running in E2B Sandbox**:
```bash
# Requires E2B_API_KEY environment variable
make demo-mysql-duckdb-supabase-e2b

# Or manually
cd testing_env
python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml
python ../osiris.py run --last-compile --e2b --verbose
```

**Troubleshooting**:
- **Missing connections**: Ensure `osiris_connections.yaml` exists with MySQL and Supabase configs
- **Authentication errors**: Check `MYSQL_PASSWORD` and `SUPABASE_SERVICE_ROLE_KEY` environment variables
- **Table exists error**: The pipeline uses `write_mode: replace` to overwrite existing data
- **DuckDB not found**: The driver is now registered in both local and E2B execution paths

### AIOP Examples

After running any pipeline, explore the AI Operation Package:

```bash
# Run a pipeline to generate AIOP
python osiris.py run examples/mysql_to_local_csv_all_tables.yaml

# View the generated AIOP
cat logs/aiop/latest.json | jq '.narrative.summary'

# Export specific run as Markdown
python osiris.py logs aiop --last --format md

# Compare with sample AIOP structure
jq 'keys' docs/examples/aiop-sample.json
```

### Quick AIOP Walkthrough

1. **Enable AIOP** (default in new installs):
   ```bash
   python osiris.py init
   # Ensure aiop.enabled: true in osiris.yaml
   ```

2. **Run any pipeline**:
   ```bash
   python osiris.py run examples/mysql_to_local_csv_all_tables.yaml
   ```

3. **Explore exports**:
   ```bash
   # AI-friendly JSON export
   ls logs/aiop/

   # Human-readable summary
   cat logs/aiop/*_runcard.md

   # Check for truncation
   jq '.metadata.truncated' logs/aiop/latest.json
   ```

See the main README.md for complete setup instructions.
