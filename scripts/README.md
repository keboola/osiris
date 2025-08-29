# Scripts

Development and testing scripts for Osiris MVP.

## Files

### `test_manual_transfer.py` - MySQL to Supabase Data Transfer

A comprehensive script that demonstrates MySQL to Supabase data transfer using the Osiris connector APIs directly (no YAML pipelines required).

#### Features

- **✅ Automatic Table Detection** - Checks if Supabase tables exist before transfer
- **🔧 Smart Table Creation** - Generates PostgreSQL CREATE TABLE statements with proper data types
- **🚀 Auto Schema Inference** - Maps MySQL types to PostgreSQL equivalents automatically
- **📋 Clean SQL Output** - Copy-pasteable SQL without log prefixes
- **🛡️ Error Handling** - Graceful handling of missing tables and connection issues
- **⚡ Batch Processing** - Configurable batch sizes for large datasets

#### Usage

**Basic transfer (with auto-detection):**
```bash
source .venv/bin/activate
python scripts/test_manual_transfer.py
```

**Show table creation SQL only:**
```bash
source .venv/bin/activate
python scripts/test_manual_transfer.py --create-tables
```

#### Workflow

1. **Auto-Detection**: Script connects to both databases and checks if target tables exist
2. **Smart Helper**: If tables are missing, displays clean CREATE TABLE SQL statements
3. **Manual Step**: User copies SQL to Supabase SQL Editor and runs it
4. **Data Transfer**: Re-run script to transfer data to existing tables

#### Environment Variables

The script automatically loads from `testing_env/.env`:

**MySQL Connection:**
- `MYSQL_HOST` - Database host (e.g., `localhost` or RDS endpoint)  
- `MYSQL_USER` - Database username
- `MYSQL_PASSWORD` - Database password
- `MYSQL_DATABASE` - Database name
- `MYSQL_PORT` - Database port (default: 3306)

**Supabase Connection:**
- `SUPABASE_PROJECT_ID` - Your Supabase project ID
- `SUPABASE_ANON_PUBLIC_KEY` - Anon public key (for basic access)
- `SUPABASE_SERVICE_ROLE_KEY` - Service role key (preferred, more permissions)

#### Configuration Options

The script uses these SupabaseWriter config options:

```python
supabase_config = {
    "url": "https://your-project.supabase.co",
    "key": "your-api-key", 
    "batch_size": 1000,           # Rows per batch
    "mode": "append",             # append/replace/upsert
    "auto_create_table": True     # Enable schema generation
}
```

#### Data Type Mapping

| MySQL Type | PostgreSQL Type | Notes |
|------------|-----------------|--------|
| `INT`, `BIGINT` | `BIGINT` | All integers become BIGINT |
| `VARCHAR`, `TEXT` | `TEXT` | Flexible text storage |
| `DATETIME`, `TIMESTAMP` | `TIMESTAMPTZ` | Timezone-aware timestamps |
| `TINYINT(1)`, `BOOLEAN` | `BOOLEAN` | Boolean values |
| `FLOAT`, `DOUBLE` | `DOUBLE PRECISION` | Floating point numbers |

#### Example Output

```bash
# When tables are missing
================================================================================
TABLE CREATION HELPER  
================================================================================
The following SQL statements need to be executed in your Supabase SQL Editor.
Go to: https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql
Copy and paste each CREATE TABLE statement:

-- Table: imported_actors
CREATE TABLE "imported_actors" (
  "actor_id" BIGINT PRIMARY KEY,
  "name" TEXT,
  "birth_year" BIGINT,
  "nationality" TEXT,
  "created_at" TIMESTAMPTZ,
  "updated_at" TIMESTAMPTZ
);
================================================================================
```

#### Troubleshooting

**"Table does not exist" errors:**
- Run with `--create-tables` flag to get the SQL
- Execute the SQL in Supabase SQL Editor
- Re-run the transfer script

**Connection errors:**
- Verify environment variables in `testing_env/.env`
- Check database connectivity and permissions
- Ensure Supabase project ID and keys are correct

**Schema mismatches:**
- The script shows actual vs expected column formats
- Manually adjust table schemas if needed
- Consider using `mode: "replace"` to recreate data

## General Usage

All scripts require virtual environment activation:

```bash
source .venv/bin/activate
python scripts/script_name.py
```
