"""Test fixtures for DuckDB streaming prototype.

This module provides sample data and fixture generators for testing
DuckDB streaming components.
"""

from pathlib import Path


def get_sample_actors_data() -> list[dict]:
    """Get sample actors data for testing.

    Returns:
        List of 10 actor records with id, name, and age fields

    Example:
        >>> actors = get_sample_actors_data()
        >>> print(len(actors))
        10
        >>> print(actors[0])
        {'id': 1, 'name': 'Tom Hanks', 'age': 67}
    """
    return [
        {"id": 1, "name": "Tom Hanks", "age": 67},
        {"id": 2, "name": "Meryl Streep", "age": 74},
        {"id": 3, "name": "Denzel Washington", "age": 69},
        {"id": 4, "name": "Cate Blanchett", "age": 54},
        {"id": 5, "name": "Morgan Freeman", "age": 86},
        {"id": 6, "name": "Viola Davis", "age": 58},
        {"id": 7, "name": "Anthony Hopkins", "age": 86},
        {"id": 8, "name": "Frances McDormand", "age": 66},
        {"id": 9, "name": "Daniel Day-Lewis", "age": 66},
        {"id": 10, "name": "Judi Dench", "age": 89},
    ]


def get_expected_filtered_actors() -> list[dict]:
    """Get expected results after filtering actors over age 70.

    Returns:
        List of actors with age > 70

    Example:
        >>> filtered = get_expected_filtered_actors()
        >>> print(len(filtered))
        4
        >>> all(actor['age'] > 70 for actor in filtered)
        True
    """
    return [
        {"id": 2, "name": "Meryl Streep", "age": 74},
        {"id": 5, "name": "Morgan Freeman", "age": 86},
        {"id": 7, "name": "Anthony Hopkins", "age": 86},
        {"id": 10, "name": "Judi Dench", "age": 89},
    ]


def get_expected_sorted_actors() -> list[dict]:
    """Get expected results after sorting actors by age descending.

    Returns:
        List of all actors sorted by age (oldest first)

    Example:
        >>> sorted_actors = get_expected_sorted_actors()
        >>> print(sorted_actors[0]['name'])
        Judi Dench
        >>> print(sorted_actors[-1]['name'])
        Cate Blanchett
    """
    return [
        {"id": 10, "name": "Judi Dench", "age": 89},
        {"id": 5, "name": "Morgan Freeman", "age": 86},
        {"id": 7, "name": "Anthony Hopkins", "age": 86},
        {"id": 2, "name": "Meryl Streep", "age": 74},
        {"id": 3, "name": "Denzel Washington", "age": 69},
        {"id": 1, "name": "Tom Hanks", "age": 67},
        {"id": 8, "name": "Frances McDormand", "age": 66},
        {"id": 9, "name": "Daniel Day-Lewis", "age": 66},
        {"id": 6, "name": "Viola Davis", "age": 58},
        {"id": 4, "name": "Cate Blanchett", "age": 54},
    ]


def create_test_csv(csv_path: Path, records: list[dict] | None = None) -> Path:
    """Create a CSV file with test data.

    Args:
        csv_path: Path where CSV file should be created
        records: List of dictionaries to write (defaults to sample actors data)

    Returns:
        Path to the created CSV file

    Raises:
        ValueError: If records list is empty or has inconsistent keys

    Example:
        >>> from pathlib import Path
        >>> csv_path = Path("/tmp/actors.csv")
        >>> create_test_csv(csv_path)
        >>> print(csv_path.exists())
        True
    """
    if records is None:
        records = get_sample_actors_data()

    if not records:
        raise ValueError("Cannot create CSV from empty records list")

    # Validate all records have the same keys
    first_keys = set(records[0].keys())
    for i, record in enumerate(records[1:], start=1):
        if set(record.keys()) != first_keys:
            raise ValueError(f"Record {i} has different keys than record 0")

    # Create parent directory if needed
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Write CSV
    with open(csv_path, "w", encoding="utf-8") as f:
        # Write header
        columns = list(records[0].keys())
        f.write(",".join(columns) + "\n")

        # Write data rows
        for record in records:
            values = [str(record[col]) for col in columns]
            f.write(",".join(values) + "\n")

    return csv_path


def get_sample_query_filter_by_age() -> str:
    """Get a sample SQL query that filters actors by age.

    Returns:
        SQL query string that selects actors over 70

    Example:
        >>> query = get_sample_query_filter_by_age()
        >>> print("WHERE age >" in query)
        True
    """
    return """
        SELECT id, name, age
        FROM actors
        WHERE age > 70
        ORDER BY id
    """


def get_sample_query_sort_by_age() -> str:
    """Get a sample SQL query that sorts actors by age.

    Returns:
        SQL query string that sorts actors by age descending

    Example:
        >>> query = get_sample_query_sort_by_age()
        >>> print("ORDER BY age DESC" in query)
        True
    """
    return """
        SELECT id, name, age
        FROM actors
        ORDER BY age DESC
    """


def get_sample_query_aggregate() -> str:
    """Get a sample SQL query that computes aggregate statistics.

    Returns:
        SQL query string that computes count, average age, min age, max age

    Example:
        >>> query = get_sample_query_aggregate()
        >>> print("AVG(age)" in query)
        True
    """
    return """
        SELECT
            COUNT(*) as total_actors,
            AVG(age) as avg_age,
            MIN(age) as min_age,
            MAX(age) as max_age
        FROM actors
    """


def get_expected_aggregate_results() -> dict:
    """Get expected results from aggregate query on sample data.

    Returns:
        Dictionary with aggregate statistics

    Example:
        >>> result = get_expected_aggregate_results()
        >>> print(result['total_actors'])
        10
        >>> print(result['avg_age'])
        70.5
    """
    return {
        "total_actors": 10,
        "avg_age": 70.5,  # (67+74+69+54+86+58+86+66+66+89)/10
        "min_age": 54,
        "max_age": 89,
    }
