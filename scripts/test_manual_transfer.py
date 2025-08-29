#!/usr/bin/env python3
"""
Manual MySQL to Supabase data transfer test.

This script demonstrates how to use the MySQL extractor and Supabase writer
directly without YAML pipelines.

Usage:
    1. Activate virtual environment: source .venv/bin/activate
    2. Run: python scripts/test_manual_transfer.py

Environment variables (automatically loaded from testing_env/.env):
    - MySQL: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
    - Supabase: SUPABASE_PROJECT_ID, SUPABASE_ANON_PUBLIC_KEY (or SUPABASE_SERVICE_ROLE_KEY)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the parent directory to Python path so we can import osiris
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from osiris.connectors.mysql import MySQLExtractor
from osiris.connectors.supabase import SupabaseWriter


def load_env_file(env_path: str) -> None:
    """Load environment variables from .env file."""
    env_file = Path(env_path)
    if not env_file.exists():
        logger.warning(f"Environment file {env_path} not found")
        return

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip('"').strip("'")
                os.environ[key] = value
                logger.debug(f"Set {key}=***")


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_supabase_tables():
    """Helper function to generate and display table creation SQL."""
    print("\n" + "=" * 80)
    print("TABLE CREATION HELPER")
    print("=" * 80)
    print("The following SQL statements need to be executed in your Supabase SQL Editor.")
    print("Go to: https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql")
    print("Copy and paste each CREATE TABLE statement:")
    print("")

    # Pre-defined schemas based on the MySQL tables we're importing
    table_schemas = {
        "imported_actors": {
            "actor_id": "BIGINT PRIMARY KEY",
            "name": "TEXT",
            "birth_year": "BIGINT",
            "nationality": "TEXT",
            "created_at": "TIMESTAMPTZ",
            "updated_at": "TIMESTAMPTZ",
        },
        "imported_directors": {
            "director_id": "BIGINT PRIMARY KEY",
            "name": "TEXT",
            "birth_year": "BIGINT",
            "nationality": "TEXT",
            "awards": "BIGINT",
            "created_at": "TIMESTAMPTZ",
            "updated_at": "TIMESTAMPTZ",
        },
        "imported_movie_actors": {
            "movie_id": "BIGINT",
            "actor_id": "BIGINT",
            "role": "TEXT",
            "is_lead_role": "BOOLEAN",
            "created_at": "TIMESTAMPTZ",
            "PRIMARY KEY": "(movie_id, actor_id)",
        },
    }

    for table_name, schema in table_schemas.items():
        print(f"-- Table: {table_name}")

        # Handle composite primary key case
        if "PRIMARY KEY" in schema:
            primary_key_def = schema.pop("PRIMARY KEY")
            column_definitions = [f'"{col}" {sql_type}' for col, sql_type in schema.items()]
            column_definitions.append(f"PRIMARY KEY {primary_key_def}")
        else:
            column_definitions = [f'"{col}" {sql_type}' for col, sql_type in schema.items()]

        create_sql = f'CREATE TABLE "{table_name}" (\n  {",\n  ".join(column_definitions)}\n);'
        print(create_sql)
        print("")

    print("=" * 80)
    print("After running these SQL statements, re-run this script to transfer data.")
    print("=" * 80)


async def test_mysql_to_supabase_transfer():
    """Test transferring data from MySQL to Supabase."""

    # Load environment variables from .env file
    env_path = os.path.join(os.path.dirname(__file__), "..", "testing_env", ".env")
    load_env_file(env_path)
    logger.info(f"Loaded environment from: {env_path}")

    # MySQL configuration
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "")
    mysql_database = os.getenv("MYSQL_DATABASE", "test")
    mysql_port = int(os.getenv("MYSQL_PORT", 3306))

    # Debug: Show what MySQL config we found
    logger.info("MySQL config:")
    logger.info(f"  - Host: {mysql_host}")
    logger.info(f"  - Port: {mysql_port}")
    logger.info(f"  - User: {mysql_user}")
    logger.info(f"  - Password: {'***' if mysql_password else 'EMPTY'}")
    logger.info(f"  - Database: {mysql_database}")

    mysql_config = {
        "host": mysql_host,
        "port": mysql_port,
        "user": mysql_user,  # MySQLClient expects "user", not "username"
        "password": mysql_password,
        "database": mysql_database,
        "pool_size": 5,
        "pool_timeout": 30,
    }

    # Supabase configuration - construct URL from project ID
    project_id = os.getenv("SUPABASE_PROJECT_ID")
    anon_key = os.getenv("SUPABASE_ANON_PUBLIC_KEY")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # Debug: Show what we found
    logger.info(f"Found SUPABASE_PROJECT_ID: {project_id[:10] + '...' if project_id else 'None'}")
    logger.info(f"Found SUPABASE_ANON_PUBLIC_KEY: {'Yes' if anon_key else 'No'}")
    logger.info(f"Found SUPABASE_SERVICE_ROLE_KEY: {'Yes' if service_key else 'No'}")

    # Use service role key if available (more permissions), otherwise anon key
    api_key = service_key if service_key else anon_key

    if not project_id or not api_key:
        raise ValueError(
            "Missing Supabase credentials. Set SUPABASE_PROJECT_ID and either "
            "SUPABASE_ANON_PUBLIC_KEY or SUPABASE_SERVICE_ROLE_KEY environment variables."
        )

    # Construct Supabase URL from project ID
    supabase_url = f"https://{project_id}.supabase.co"

    supabase_config = {
        "url": supabase_url,
        "key": api_key,
        "batch_size": 1000,
        "mode": "append",  # or "replace", "upsert"
        "auto_create_table": True,  # Enable automatic table creation
    }

    # Initialize extractors and writers
    mysql_extractor = MySQLExtractor(mysql_config)
    supabase_writer = SupabaseWriter(supabase_config)

    try:
        # Connect to both databases
        logger.info("Connecting to MySQL...")
        await mysql_extractor.connect()

        logger.info("Connecting to Supabase...")
        await supabase_writer.connect()

        # List available MySQL tables
        logger.info("Discovering MySQL tables...")
        tables = await mysql_extractor.list_tables()
        logger.info(f"Found tables: {tables}")

        if not tables:
            logger.warning("No tables found in MySQL database")
            return

        # Check if tables exist first
        tables_need_creation = []
        for table_name in tables[:3]:  # Limit to first 3 tables for testing
            target_table = f"imported_{table_name}"

            # Quick test to see if table exists
            try:
                # Try a simple query to check table existence
                test_query = (
                    supabase_writer.client.table(target_table).select("*").limit(0).execute()
                )
                logger.info(f"✓ Table {target_table} exists")
            except Exception as e:
                if "PGRST205" in str(e) or "not found" in str(e).lower():
                    tables_need_creation.append(target_table)
                    logger.warning(f"✗ Table {target_table} does not exist")

        # If tables need to be created, show the helper
        if tables_need_creation:
            logger.info(
                f"\nFound {len(tables_need_creation)} missing tables: {tables_need_creation}"
            )
            await create_supabase_tables()
            print("\nPlease create the tables in Supabase and re-run this script.")
            return

        logger.info("✓ All required tables exist. Proceeding with data transfer...")

        # For each table, get info and transfer data
        for table_name in tables[:3]:  # Limit to first 3 tables for testing
            logger.info(f"\n--- Processing table: {table_name} ---")

            # Get table information
            table_info = await mysql_extractor.get_table_info(table_name)
            logger.info(f"Table {table_name}:")
            logger.info(f"  - Columns: {table_info.columns}")
            logger.info(f"  - Row count: {table_info.row_count}")
            logger.info(f"  - Primary keys: {table_info.primary_keys}")

            # Extract sample data
            logger.info(f"Extracting sample data from {table_name}...")
            sample_df = await mysql_extractor.sample_table(table_name, size=100)
            logger.info(f"Extracted {len(sample_df)} rows")

            # Convert to list of dicts for Supabase
            data = sample_df.to_dict("records")

            # Load into Supabase
            target_table = f"imported_{table_name}"  # Prefix to avoid conflicts
            logger.info(f"Loading data into Supabase table: {target_table}")

            try:
                success = await supabase_writer.insert_data(target_table, data)
                if success:
                    logger.info(f"✓ Successfully transferred {len(data)} rows to {target_table}")
                else:
                    logger.error(f"✗ Failed to transfer data to {target_table}")
            except Exception as e:
                logger.error(f"✗ Error transferring to {target_table}: {e}")
                logger.info(
                    "  This shouldn't happen since we checked table existence, but the table might have schema issues"
                )

                # Show sample data format for debugging
                if data:
                    logger.info(f"  Sample data format: {list(data[0].keys())}")

        # Example: Execute custom query and transfer results
        logger.info("\n--- Custom Query Example ---")
        custom_query = (
            "SELECT * FROM information_schema.tables WHERE table_schema = DATABASE() LIMIT 5"
        )

        try:
            custom_df = await mysql_extractor.execute_query(custom_query)
            logger.info(f"Custom query returned {len(custom_df)} rows")
            logger.info(f"Columns: {list(custom_df.columns)}")

            # Could transfer this to Supabase too:
            # custom_data = custom_df.to_dict('records')
            # await supabase_writer.insert_data("mysql_table_info", custom_data)

        except Exception as e:
            logger.error(f"Custom query failed: {e}")

    except Exception as e:
        logger.error(f"Transfer failed: {e}")
        raise

    finally:
        # Clean up connections
        logger.info("\nDisconnecting...")
        await mysql_extractor.disconnect()
        await supabase_writer.disconnect()
        logger.info("Transfer test completed!")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="MySQL to Supabase data transfer test")
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Show SQL for creating required tables in Supabase",
    )
    args = parser.parse_args()

    if args.create_tables:
        logger.info("Showing table creation SQL...")
        await create_supabase_tables()
        return

    logger.info("Starting MySQL to Supabase transfer test...")
    logger.info("Make sure you have:")
    logger.info("1. MySQL database accessible with test data")
    logger.info("2. Supabase project with matching tables created")
    logger.info("3. Environment variables set (see script comments)")
    logger.info("")
    logger.info(
        "TIP: Run 'python scripts/test_manual_transfer.py --create-tables' to get table creation SQL"
    )

    await test_mysql_to_supabase_transfer()


if __name__ == "__main__":
    asyncio.run(main())
