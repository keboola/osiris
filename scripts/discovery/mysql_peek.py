#!/usr/bin/env python3
"""
MySQL Data Discovery Helper
Explores available tables and suggests DuckDB transformations.
"""

import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from sqlalchemy import create_engine

from osiris.core.config import resolve_connection


def get_connection_url():
    """Get MySQL connection URL from Osiris config."""
    try:
        # Try to resolve MySQL connection (uses osiris_connections.yaml + env vars)
        conn_config = resolve_connection("mysql", "db_movies")

        # Build SQLAlchemy URL
        host = conn_config.get("host", "localhost")
        port = conn_config.get("port", 3306)
        database = conn_config.get("database", "mysql")
        user = conn_config.get("user", "root")
        password = conn_config.get("password", "")

        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        return url
    except Exception as e:
        print(f"Failed to resolve MySQL connection: {e}")
        print("Ensure MYSQL_PASSWORD is set and osiris_connections.yaml exists")
        sys.exit(1)


def discover_tables(engine):
    """List all tables in the database."""
    query = "SHOW TABLES"
    df = pd.read_sql(query, engine)
    return df.iloc[:, 0].tolist()


def describe_table(engine, table_name):
    """Get schema info for a table."""
    query = f"DESCRIBE `{table_name}`"
    return pd.read_sql(query, engine)


def sample_data(engine, table_name, limit=5):
    """Get sample rows from a table."""
    # Safe: table_name from SHOW TABLES, limit is integer
    query = f"SELECT * FROM `{table_name}` LIMIT {limit}"  # nosec B608
    return pd.read_sql(query, engine)


def count_rows(engine, table_name):
    """Count rows in a table."""
    # Safe: table_name from SHOW TABLES, not user input
    query = f"SELECT COUNT(*) as count FROM `{table_name}`"  # nosec B608
    result = pd.read_sql(query, engine)
    return result["count"][0]


def suggest_transforms(engine, tables):
    """Suggest interesting DuckDB transformations based on schema."""
    suggestions = []

    # Check for movies table
    if "movies" in tables:
        movies_schema = describe_table(engine, "movies")
        if "director_id" in movies_schema["Field"].values:
            suggestions.append(
                {
                    "name": "Directors Statistics",
                    "description": "Count movies and average runtime per director",
                    "base_table": "movies",
                    "sql": """
                    SELECT
                        director_id,
                        COUNT(*) as movie_count,
                        AVG(runtime) as avg_runtime,
                        MIN(release_year) as first_movie_year,
                        MAX(release_year) as latest_movie_year
                    FROM input_df
                    WHERE director_id IS NOT NULL
                    GROUP BY director_id
                    HAVING COUNT(*) > 1
                    ORDER BY movie_count DESC
                    LIMIT 20
                """,
                }
            )

    # Check for reviews/ratings
    if "reviews" in tables:
        suggestions.append(
            {
                "name": "Movie Ratings Summary",
                "description": "Average rating and review count per movie",
                "base_table": "reviews",
                "sql": """
                SELECT
                    movie_id,
                    COUNT(*) as review_count,
                    AVG(rating) as avg_rating,
                    MIN(rating) as min_rating,
                    MAX(rating) as max_rating
                FROM input_df
                GROUP BY movie_id
                HAVING COUNT(*) > 5
                ORDER BY avg_rating DESC
                LIMIT 50
            """,
            }
        )

    # Check for actors
    if "movie_actors" in tables:
        suggestions.append(
            {
                "name": "Actor Collaboration Network",
                "description": "Count of movies per actor",
                "base_table": "movie_actors",
                "sql": """
                SELECT
                    actor_id,
                    COUNT(DISTINCT movie_id) as movie_count,
                    COUNT(*) as role_count
                FROM input_df
                GROUP BY actor_id
                HAVING COUNT(DISTINCT movie_id) > 3
                ORDER BY movie_count DESC
                LIMIT 30
            """,
            }
        )

    # Generic aggregation for any table with numeric columns
    for table in tables[:3]:  # Check first 3 tables
        schema = describe_table(engine, table)
        numeric_cols = schema[schema["Type"].str.contains("int|decimal|float", case=False)][
            "Field"
        ].tolist()
        if len(numeric_cols) > 1 and table not in ["movies", "reviews", "movie_actors"]:
            suggestions.append(
                {
                    "name": f"{table.title()} Statistics",
                    "description": f"Basic statistics for {table}",
                    "base_table": table,
                    # Safe: column names from schema, not user input
                    "sql": f"""
                    SELECT
                        COUNT(*) as total_rows,
                        {', '.join([f'AVG({col}) as avg_{col}' for col in numeric_cols[:2]])}
                    FROM input_df
                """,  # nosec B608
                }
            )
            break

    return suggestions


def main():
    """Main discovery flow."""
    print("=" * 60)
    print("MySQL Data Discovery for DuckDB Transform Demo")
    print("=" * 60)

    # Connect to MySQL
    print("\nConnecting to MySQL...")
    engine = create_engine(get_connection_url())

    # Discover tables
    print("\nDiscovering tables...")
    tables = discover_tables(engine)
    print(f"Found {len(tables)} tables: {', '.join(tables[:10])}")
    if len(tables) > 10:
        print(f"  ... and {len(tables) - 10} more")

    # Show details for key tables
    print("\n" + "=" * 60)
    print("TABLE DETAILS")
    print("=" * 60)

    for table in ["movies", "directors", "actors", "reviews", "movie_actors"][:3]:
        if table in tables:
            print(f"\n📊 Table: {table}")
            print(f"   Rows: {count_rows(engine, table):,}")

            # Show schema
            schema = describe_table(engine, table)
            print("   Schema:")
            for _, row in schema.iterrows():
                print(f"     - {row['Field']}: {row['Type']}")

            # Show sample
            sample = sample_data(engine, table, 3)
            print(f"   Sample data ({len(sample)} rows):")
            print(sample.to_string(index=False, max_colwidth=30))

    # Suggest transformations
    print("\n" + "=" * 60)
    print("SUGGESTED DUCKDB TRANSFORMATIONS")
    print("=" * 60)

    suggestions = suggest_transforms(engine, tables)

    for i, suggestion in enumerate(suggestions[:3], 1):
        print(f"\n{i}. {suggestion['name']}")
        print(f"   Base table: {suggestion['base_table']}")
        print(f"   Description: {suggestion['description']}")
        print("   SQL Preview:")
        for line in suggestion["sql"].strip().split("\n"):
            print(f"      {line}")

    # Recommend the best option
    if suggestions:
        print("\n" + "=" * 60)
        print("RECOMMENDATION")
        print("=" * 60)
        best = suggestions[0]
        print(f"\n✅ Recommended transform: {best['name']}")
        print(f"   This aggregates {best['base_table']} data for meaningful statistics")
        print("   Output will be ~20-50 rows suitable for Supabase target table")

    print("\n" + "=" * 60)
    print("Discovery complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
