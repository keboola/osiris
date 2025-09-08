#!/usr/bin/env python3
"""Test script to demonstrate driver-based pipeline execution with mock data."""

import sys
import os
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from osiris.core.runner_v0 import RunnerV0


def mock_mysql_data(query, engine):
    """Mock MySQL data based on query."""
    if "actors" in query.lower():
        return pd.DataFrame({
            "actor_id": [1, 2, 3, 4, 5],
            "first_name": ["Tom", "Morgan", "Meryl", "Robert", "Scarlett"],
            "last_name": ["Hanks", "Freeman", "Streep", "De Niro", "Johansson"],
            "birth_year": [1956, 1937, 1949, 1943, 1984]
        })
    elif "directors" in query.lower():
        return pd.DataFrame({
            "director_id": [1, 2, 3],
            "name": ["Steven Spielberg", "Christopher Nolan", "Quentin Tarantino"],
            "birth_year": [1946, 1970, 1963]
        })
    elif "movie_actors" in query.lower():
        return pd.DataFrame({
            "movie_id": [1, 1, 2, 2, 3],
            "actor_id": [1, 2, 3, 4, 5],
            "role": ["Forrest", "Red", "Sophie", "Travis", "Black Widow"]
        })
    elif "movies" in query.lower():
        return pd.DataFrame({
            "movie_id": [1, 2, 3],
            "title": ["Forrest Gump", "The Devil Wears Prada", "Avengers"],
            "year": [1994, 2006, 2012],
            "director_id": [1, 2, 3]
        })
    elif "reviews" in query.lower():
        return pd.DataFrame({
            "review_id": [1, 2, 3, 4, 5],
            "movie_id": [1, 1, 2, 3, 3],
            "rating": [9.0, 8.5, 7.5, 8.0, 9.5],
            "review_text": ["Amazing!", "Heartwarming", "Great fashion", "Action-packed", "Best Marvel movie"]
        })
    else:
        return pd.DataFrame()


def main():
    """Run the mysql_to_local_csv pipeline with mock data."""
    print("🚀 Running MySQL to CSV pipeline with mock data...")
    
    # Find the last compiled manifest
    logs_dir = Path("logs")
    compile_dirs = sorted([d for d in logs_dir.glob("compile_*") if d.is_dir()])
    if not compile_dirs:
        print("❌ No compiled pipelines found. Run 'osiris compile' first.")
        return 1
    
    latest_compile = compile_dirs[-1]
    manifest_path = latest_compile / "compiled" / "manifest.yaml"
    
    if not manifest_path.exists():
        print(f"❌ Manifest not found: {manifest_path}")
        return 1
    
    print(f"📄 Using manifest: {manifest_path}")
    
    # Create output directory
    output_dir = Path("mock_run_output")
    output_dir.mkdir(exist_ok=True)
    
    # Create runner
    runner = RunnerV0(str(manifest_path), output_dir=str(output_dir))
    
    # Mock MySQL engine and data
    with patch("osiris.drivers.mysql_extractor_driver.sa.create_engine") as mock_create_engine:
        with patch("osiris.drivers.mysql_extractor_driver.pd.read_sql_query") as mock_read_sql:
            # Setup mocks
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine
            mock_read_sql.side_effect = mock_mysql_data
            
            # Mock connection resolution and set env var
            with patch("osiris.core.config.resolve_connection") as mock_resolve:
                mock_resolve.return_value = {
                    "host": "mock-mysql-host",
                    "port": 3306,
                    "database": "mock_movies_db",
                    "user": "mock_user",
                    "password": "mock_password"  # pragma: allowlist secret
                }
                
                # Also need to set env var for the config validation
                with patch.dict("os.environ", {"MYSQL_PASSWORD": "mock_password"}):  # pragma: allowlist secret
                    # Run the pipeline
                    print("⚙️  Executing pipeline...")
                    success = runner.run()
    
    if success:
        print("✅ Pipeline executed successfully!")
        
        # Check output files
        output_csv_dir = Path("output")
        if output_csv_dir.exists():
            csv_files = list(output_csv_dir.glob("*.csv"))
            if csv_files:
                print(f"\n📊 Generated {len(csv_files)} CSV files:")
                for csv_file in sorted(csv_files):
                    df = pd.read_csv(csv_file)
                    print(f"  - {csv_file.name}: {len(df)} rows, {len(df.columns)} columns")
                    print(f"    Columns: {', '.join(sorted(df.columns))}")
            else:
                print("⚠️  No CSV files found in output directory")
        else:
            print("⚠️  Output directory not found")
        
        return 0
    else:
        print("❌ Pipeline execution failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())