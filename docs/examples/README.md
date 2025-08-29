# Osiris MVP Examples

Example pipeline files demonstrating the OML (Osiris Markup Language) format.

## Files

- **`sample_pipeline.yaml`** - MySQL pipeline example
- **`top_customers_revenue.yaml`** - Supabase pipeline example

## Usage

These files show the OML v1.0-MVP format. To generate your own pipelines:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Initialize configuration
python osiris.py init

# Generate pipeline through conversation
python osiris.py chat

# Run example pipeline with dry-run
python osiris.py run examples/sample_pipeline.yaml --dry-run
```

See the main README.md for complete setup instructions.
