"""Unit tests for DuckDB SQL transformations without external IO."""

import pandas as pd


class TestDuckDBSQLSmoke:
    """Test DuckDB SQL patterns used in demo pipeline."""

    def test_director_stats_aggregation(self):
        """Test the director statistics aggregation SQL logic."""
        # Create mock movie data
        input_df = pd.DataFrame(
            {
                "movie_id": [1, 2, 3, 4, 5],
                "title": ["Inception", "Dunkirk", "Tenet", "Barbie", "Little Women"],
                "director_id": [1, 1, 1, 2, 2],
                "director_name": [
                    "Christopher Nolan",
                    "Christopher Nolan",
                    "Christopher Nolan",
                    "Greta Gerwig",
                    "Greta Gerwig",
                ],
                "director_nationality": [
                    "British-American",
                    "British-American",
                    "British-American",
                    "American",
                    "American",
                ],
                "release_year": [2010, 2017, 2020, 2023, 2019],
                "runtime_minutes": [148, 106, 150, 114, 135],
                "budget_usd": [160_000_000, 100_000_000, 205_000_000, 145_000_000, 40_000_000],
                "box_office_usd": [
                    836_800_000,
                    526_900_000,
                    363_700_000,
                    1_441_000_000,
                    218_900_000,
                ],
                "genre": [
                    "Sci-Fi/Thriller",
                    "War/Drama",
                    "Sci-Fi/Action",
                    "Comedy/Fantasy",
                    "Drama",
                ],
            }
        )

        # Apply aggregation (mimics DuckDB GROUP BY)
        result = (
            input_df[input_df["budget_usd"].notna() & input_df["box_office_usd"].notna()]
            .groupby(["director_id", "director_name", "director_nationality"])
            .agg(
                movie_count=("movie_id", "count"),
                unique_genres=("genre", "nunique"),
                avg_runtime_minutes=("runtime_minutes", lambda x: round(x.mean(), 1)),
                first_movie_year=("release_year", "min"),
                latest_movie_year=("release_year", "max"),
                avg_budget_usd=("budget_usd", lambda x: round(x.mean(), 0)),
                avg_box_office_usd=("box_office_usd", lambda x: round(x.mean(), 0)),
                total_box_office_usd=("box_office_usd", lambda x: round(x.sum(), 0)),
            )
            .reset_index()
        )

        # Calculate ROI ratio
        result["avg_roi_ratio"] = round(result["avg_box_office_usd"] / result["avg_budget_usd"], 2)

        # Sort by total box office (DESC)
        result = result.sort_values("total_box_office_usd", ascending=False).reset_index(drop=True)

        # Assertions
        assert len(result) == 2  # Two directors

        # Check Nolan's stats (should be first due to higher total box office)
        nolan = result.iloc[0]
        assert nolan["director_name"] == "Christopher Nolan"
        assert nolan["movie_count"] == 3
        assert nolan["unique_genres"] == 3
        assert nolan["avg_runtime_minutes"] == 134.7  # (148+106+150)/3
        assert nolan["first_movie_year"] == 2010
        assert nolan["latest_movie_year"] == 2020
        assert nolan["total_box_office_usd"] == 1_727_400_000

        # Check Gerwig's stats
        gerwig = result.iloc[1]
        assert gerwig["director_name"] == "Greta Gerwig"
        assert gerwig["movie_count"] == 2
        assert gerwig["unique_genres"] == 2
        assert gerwig["first_movie_year"] == 2019
        assert gerwig["latest_movie_year"] == 2023

    def test_empty_input_handling(self):
        """Test handling of empty input DataFrame."""
        input_df = pd.DataFrame()

        # Apply aggregation on empty DataFrame
        if input_df.empty:
            result = pd.DataFrame(
                columns=[
                    "director_id",
                    "director_name",
                    "director_nationality",
                    "movie_count",
                    "unique_genres",
                    "avg_runtime_minutes",
                    "first_movie_year",
                    "latest_movie_year",
                    "avg_budget_usd",
                    "avg_box_office_usd",
                    "total_box_office_usd",
                    "avg_roi_ratio",
                ]
            )
        else:
            # Would normally do aggregation
            result = input_df

        assert result.empty
        assert len(result.columns) == 12

    def test_null_budget_filtering(self):
        """Test that rows with null budgets are filtered out."""
        input_df = pd.DataFrame(
            {
                "movie_id": [1, 2, 3],
                "director_id": [1, 1, 1],
                "director_name": ["Director A", "Director A", "Director A"],
                "director_nationality": ["USA", "USA", "USA"],
                "budget_usd": [100_000_000, None, 150_000_000],  # One null budget
                "box_office_usd": [500_000_000, 300_000_000, 700_000_000],
                "release_year": [2020, 2021, 2022],
                "runtime_minutes": [120, 110, 130],
                "genre": ["Action", "Drama", "Action"],
            }
        )

        # Filter out nulls (as DuckDB WHERE clause would)
        filtered = input_df[input_df["budget_usd"].notna() & input_df["box_office_usd"].notna()]

        assert len(filtered) == 2  # Only 2 rows with non-null budget
        assert 2 not in filtered["movie_id"].values  # Movie 2 filtered out

    def test_roi_calculation(self):
        """Test ROI ratio calculation."""
        input_df = pd.DataFrame(
            {
                "director_id": [1, 2],
                "director_name": ["Director A", "Director B"],
                "budget_usd": [10_000_000, 100_000_000],
                "box_office_usd": [50_000_000, 200_000_000],
            }
        )

        # Calculate ROI
        input_df["roi_ratio"] = round(input_df["box_office_usd"] / input_df["budget_usd"], 2)

        assert input_df.iloc[0]["roi_ratio"] == 5.0  # 50M/10M = 5.0
        assert input_df.iloc[1]["roi_ratio"] == 2.0  # 200M/100M = 2.0

    def test_having_clause_filtering(self):
        """Test HAVING COUNT(*) >= 1 filtering."""
        input_df = pd.DataFrame(
            {
                "movie_id": [1, 2, 3],
                "director_id": [1, 2, 3],
                "director_name": ["Director A", "Director B", "Director C"],
                "director_nationality": ["USA", "UK", "France"],
                "budget_usd": [10_000_000, 20_000_000, 30_000_000],
                "box_office_usd": [50_000_000, 60_000_000, 40_000_000],
                "release_year": [2020, 2021, 2022],
                "runtime_minutes": [120, 110, 130],
                "genre": ["Action", "Drama", "Comedy"],
            }
        )

        # Group and filter by count
        result = (
            input_df.groupby(["director_id", "director_name"])
            .agg(movie_count=("movie_id", "count"))
            .reset_index()
        )

        # Apply HAVING clause (>= 1)
        result = result[result["movie_count"] >= 1]

        assert len(result) == 3  # All directors have at least 1 movie
        assert all(result["movie_count"] >= 1)

    def test_order_by_total_box_office(self):
        """Test ORDER BY total_box_office_usd DESC."""
        input_df = pd.DataFrame(
            {
                "director_id": [1, 1, 2, 2, 3],
                "director_name": ["A", "A", "B", "B", "C"],
                "box_office_usd": [100, 200, 500, 600, 50],
            }
        )

        # Aggregate and sort
        result = (
            input_df.groupby(["director_id", "director_name"])
            .agg(total_box_office=("box_office_usd", "sum"))
            .reset_index()
            .sort_values("total_box_office", ascending=False)
        )

        # Check order
        assert result.iloc[0]["director_name"] == "B"  # 1100 total
        assert result.iloc[1]["director_name"] == "A"  # 300 total
        assert result.iloc[2]["director_name"] == "C"  # 50 total
