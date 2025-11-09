"""
PostHog API Client

Handles all interactions with PostHog API (HogQL Query API, Persons API, etc.)

Implements SEEK-based pagination strategy (not OFFSET) to avoid performance
degradation on large datasets. Uses timestamp + uuid for deterministic pagination.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Iterator, Any, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# Custom exceptions
class PostHogClientError(Exception):
    """Base exception for PostHog API errors"""
    pass


class PostHogAuthenticationError(PostHogClientError):
    """Authentication failed (401/403)"""
    pass


class PostHogRateLimitError(PostHogClientError):
    """Rate limit exceeded (429)"""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class PostHogNetworkError(PostHogClientError):
    """Network connectivity failure"""
    pass


class PostHogClient:
    """Client for PostHog HogQL Query API and Persons API"""

    # Rate limiting: PostHog allows 2,400 requests/hour
    RATE_LIMIT_PER_HOUR = 2400
    REQUEST_TIMEOUT = 30.0

    def __init__(self, base_url: str, api_key: str, project_id: str):
        """
        Initialize PostHog API client

        Args:
            base_url: Base URL (e.g., https://us.posthog.com)
            api_key: Personal API key from PostHog settings
            project_id: PostHog project ID
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.project_id = str(project_id)

        self.session = self._create_session()

        # Rate limiting tracking
        self._request_times: list[float] = []

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic for non-rate-limit errors"""
        session = requests.Session()

        # Only retry on server errors (5xx), not on 429 (rate limit)
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def test_connection(self, timeout: float = 2.0) -> bool:
        """
        Test API connectivity with a simple query

        Args:
            timeout: Request timeout in seconds

        Returns:
            True if connection successful

        Raises:
            PostHogAuthenticationError: If auth fails
            PostHogNetworkError: If network fails
            PostHogClientError: If other error occurs
        """
        try:
            self.execute_hogql_query("SELECT 1 LIMIT 1", timeout=timeout)
            return True
        except PostHogAuthenticationError:
            raise
        except requests.exceptions.Timeout as e:
            raise PostHogNetworkError(f"Connection timeout ({timeout}s)") from e
        except requests.exceptions.ConnectionError as e:
            raise PostHogNetworkError(f"Connection failed: {e}") from e

    def execute_hogql_query(
        self,
        query: str,
        timeout: float = REQUEST_TIMEOUT,
        max_retries: int = 5
    ) -> dict[str, Any]:
        """
        Execute a HogQL query with exponential backoff on rate limit errors

        Args:
            query: HogQL query string
            timeout: Request timeout in seconds
            max_retries: Maximum retries on rate limit (429)

        Returns:
            Query result dict with 'results' and 'columns' keys

        Raises:
            PostHogAuthenticationError: If 401/403
            PostHogRateLimitError: If rate limited after retries
            PostHogClientError: On other errors
        """
        url = urljoin(self.base_url, f"/api/projects/{self.project_id}/query/")
        headers = self._get_headers()

        payload = {
            "query": {
                "kind": "HogQLQuery",
                "query": query
            }
        }

        retry_count = 0
        while retry_count <= max_retries:
            try:
                # Rate limit check before making request
                self._check_rate_limit()

                logger.debug(f"Executing HogQL query: {query[:100]}...")
                response = self.session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )

                # Track request time for rate limiting
                self._request_times.append(time.time())

                if response.status_code == 401:
                    raise PostHogAuthenticationError("Invalid API key (401)")
                elif response.status_code == 403:
                    raise PostHogAuthenticationError("Access forbidden (403)")
                elif response.status_code == 404:
                    raise PostHogClientError(f"Project {self.project_id} not found (404)")
                elif response.status_code == 429:
                    # Rate limit hit - exponential backoff
                    retry_after = self._get_retry_after(response)
                    backoff = min(2 ** retry_count, 16)  # Cap at 16 seconds
                    sleep_time = max(backoff, retry_after)

                    retry_count += 1
                    if retry_count > max_retries:
                        raise PostHogRateLimitError(
                            f"Rate limit exceeded after {max_retries} retries",
                            retry_after=retry_after
                        )

                    logger.warning(
                        f"Rate limited (429). Retry {retry_count}/{max_retries} "
                        f"after {sleep_time}s (Retry-After: {retry_after}s)"
                    )
                    time.sleep(sleep_time)
                    continue

                response.raise_for_status()
                result = response.json()

                logger.debug(f"Query succeeded. Results: {len(result.get('results', []))} rows")
                return result

            except requests.exceptions.Timeout as e:
                raise PostHogNetworkError(f"Request timeout ({timeout}s): {e}") from e
            except requests.exceptions.ConnectionError as e:
                raise PostHogNetworkError(f"Connection error: {e}") from e
            except requests.exceptions.RequestException as e:
                if response.status_code >= 500:
                    # Transient error - will retry via session retry logic
                    raise PostHogClientError(f"Server error {response.status_code}: {e}") from e
                raise PostHogClientError(f"Request failed: {e}") from e

        raise PostHogRateLimitError("Max retries exhausted on rate limit")

    def iterate_events(
        self,
        since: datetime,
        until: datetime,
        event_types: Optional[list[str]] = None,
        page_size: int = 1000,
        last_timestamp: Optional[str] = None,
        last_uuid: Optional[str] = None
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate through events using SEEK-based pagination

        Uses SEEK strategy (WHERE timestamp > last_timestamp OR
        (timestamp = last_timestamp AND uuid > last_uuid)) instead of OFFSET
        to avoid performance degradation on large datasets.

        Args:
            since: Start timestamp (datetime, timezone-aware)
            until: End timestamp (datetime, timezone-aware)
            event_types: Filter by event types (optional)
            page_size: Rows per page (100-10000)
            last_timestamp: Resume from this timestamp (for pagination)
            last_uuid: Resume from this UUID (for pagination)

        Yields:
            Individual event dicts

        Raises:
            PostHogAuthenticationError: If auth fails
            PostHogRateLimitError: If rate limited
            PostHogClientError: On other errors
        """
        # Normalize datetimes for logging
        since_iso = self._to_iso_string(since)
        until_iso = self._to_iso_string(until)

        logger.info(
            f"Starting event iteration: {since_iso} to {until_iso}, "
            f"page_size={page_size}"
        )

        # Format timestamps for HogQL (requires toDateTime() wrapper)
        since_hogql = since.strftime('%Y-%m-%d %H:%M:%S')
        until_hogql = until.strftime('%Y-%m-%d %H:%M:%S')

        # Build WHERE clause
        where_parts = [
            f"timestamp >= toDateTime('{since_hogql}')",
            f"timestamp < toDateTime('{until_hogql}')"
        ]

        if event_types:
            event_filter = ", ".join([f"'{t}'" for t in event_types])
            where_parts.append(f"event IN ({event_filter})")

        # Add SEEK pagination if resuming
        if last_timestamp and last_uuid:
            # Clean timestamp (remove microseconds if present)
            last_ts_clean = last_timestamp[:19] if len(last_timestamp) > 19 else last_timestamp
            where_parts.append(
                f"(timestamp > toDateTime('{last_ts_clean}') OR "
                f"(timestamp = toDateTime('{last_ts_clean}') AND uuid > '{last_uuid}'))"
            )

        where_clause = " AND ".join(where_parts)

        # Build HogQL query
        # Note: person properties are NOT available in events table via HogQL
        # Only event properties are included
        query = (
            f"SELECT uuid, event, timestamp, distinct_id, person_id, properties "  # nosec B608
            f"FROM events "
            f"WHERE {where_clause} "
            f"ORDER BY timestamp ASC, uuid ASC "
            f"LIMIT {page_size}"
        )

        page_num = 0
        total_yielded = 0

        while True:
            try:
                logger.debug(f"Fetching page {page_num + 1}...")
                result = self.execute_hogql_query(query)

                rows = result.get("results", [])
                columns = result.get("columns", [])

                if not rows:
                    logger.info(
                        f"Event iteration complete. Total yielded: {total_yielded}"
                    )
                    break

                logger.debug(f"Page {page_num + 1}: {len(rows)} rows")

                # Convert list rows to dicts using column names
                for row in rows:
                    # PostHog returns results as list of lists, not list of dicts
                    # Convert: [uuid, event, timestamp, ...] -> {uuid: ..., event: ..., ...}
                    event_dict = dict(zip(columns, row))
                    yield event_dict
                    total_yielded += 1

                # If we got fewer rows than page_size, we're done
                if len(rows) < page_size:
                    logger.info(f"Final page. Total yielded: {total_yielded}")
                    break

                # Update SEEK parameters for next page
                # Last row is still a list at this point, convert to dict
                last_row = rows[-1]
                last_row_dict = dict(zip(columns, last_row))
                last_timestamp = last_row_dict.get("timestamp")
                last_uuid = last_row_dict.get("uuid")

                # Format last_timestamp for HogQL
                # It comes back from PostHog in format like '2025-11-08 16:08:16.385000'
                # Extract just the datetime part (without microseconds for cleaner query)
                last_ts_clean = last_timestamp[:19] if last_timestamp else None

                # Rebuild query with new SEEK parameters
                where_parts_updated = [
                    f"timestamp >= toDateTime('{since_hogql}')",
                    f"timestamp < toDateTime('{until_hogql}')"
                ]

                if event_types:
                    event_filter = ", ".join([f"'{t}'" for t in event_types])
                    where_parts_updated.append(f"event IN ({event_filter})")

                if last_ts_clean:
                    where_parts_updated.append(
                        f"(timestamp > toDateTime('{last_ts_clean}') OR "
                        f"(timestamp = toDateTime('{last_ts_clean}') AND uuid > '{last_uuid}'))"
                    )

                where_clause = " AND ".join(where_parts_updated)
                query = (
                    f"SELECT uuid, event, timestamp, distinct_id, person_id, properties "  # nosec B608
                    f"FROM events "
                    f"WHERE {where_clause} "
                    f"ORDER BY timestamp ASC, uuid ASC "
                    f"LIMIT {page_size}"
                )

                page_num += 1

            except PostHogRateLimitError as e:
                logger.error(f"Rate limit hit during event iteration: {e}")
                raise

    def iterate_persons(
        self,
        page_size: int = 1000,
        last_created_at: Optional[str] = None,
        last_id: Optional[str] = None
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate through persons using SEEK-based pagination

        Args:
            page_size: Rows per page (100-10000)
            last_created_at: Resume from this timestamp (for pagination)
            last_id: Resume from this ID (for pagination)

        Yields:
            Individual person dicts

        Raises:
            PostHogAuthenticationError: If auth fails
            PostHogRateLimitError: If rate limited
            PostHogClientError: On other errors
        """
        logger.info(f"Starting person iteration: page_size={page_size}")

        # Build WHERE clause for SEEK pagination if resuming
        where_parts = []
        if last_created_at and last_id:
            # Clean timestamp (remove microseconds if present)
            last_ts_clean = last_created_at[:19] if len(last_created_at) > 19 else last_created_at
            where_parts.append(
                f"(created_at > toDateTime('{last_ts_clean}') OR "
                f"(created_at = toDateTime('{last_ts_clean}') AND id > '{last_id}'))"
            )

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        query = (
            f"SELECT id, created_at, properties, is_identified "  # nosec B608
            f"FROM persons {where_clause} "
            f"ORDER BY created_at ASC, id ASC "
            f"LIMIT {page_size}"
        )

        page_num = 0
        total_yielded = 0

        while True:
            try:
                logger.debug(f"Fetching persons page {page_num + 1}...")
                result = self.execute_hogql_query(query)

                rows = result.get("results", [])
                columns = result.get("columns", [])

                if not rows:
                    logger.info(f"Person iteration complete. Total yielded: {total_yielded}")
                    break

                logger.debug(f"Page {page_num + 1}: {len(rows)} rows")

                # Convert list rows to dicts using column names
                for row in rows:
                    person_dict = dict(zip(columns, row))
                    yield person_dict
                    total_yielded += 1

                # If we got fewer rows than page_size, we're done
                if len(rows) < page_size:
                    logger.info(f"Final page. Total yielded: {total_yielded}")
                    break

                # Update SEEK parameters for next page
                last_row = rows[-1]
                last_row_dict = dict(zip(columns, last_row))
                last_created_at = last_row_dict.get("created_at")
                last_id = last_row_dict.get("id")

                # Format timestamp for HogQL
                last_ts_clean = last_created_at[:19] if last_created_at and len(last_created_at) > 19 else last_created_at

                where_clause = (
                    f"WHERE (created_at > toDateTime('{last_ts_clean}') OR "
                    f"(created_at = toDateTime('{last_ts_clean}') AND id > '{last_id}'))"
                )

                query = (
                    f"SELECT id, created_at, properties, is_identified "  # nosec B608
                    f"FROM persons {where_clause} "
                    f"ORDER BY created_at ASC, id ASC "
                    f"LIMIT {page_size}"
                )

                page_num += 1

            except PostHogRateLimitError as e:
                logger.error(f"Rate limit hit during person iteration: {e}")
                raise

    def iterate_sessions(
        self,
        since: datetime,
        until: datetime,
        page_size: int = 1000,
        last_start_timestamp: Optional[str] = None,
        last_session_id: Optional[str] = None
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate through sessions using SEEK-based pagination

        Args:
            since: Start timestamp (datetime, timezone-aware)
            until: End timestamp (datetime, timezone-aware)
            page_size: Rows per page (100-10000)
            last_start_timestamp: Resume from this timestamp (for pagination)
            last_session_id: Resume from this session_id (for pagination)

        Yields:
            Individual session dicts

        Raises:
            PostHogAuthenticationError: If auth fails
            PostHogRateLimitError: If rate limited
            PostHogClientError: On other errors
        """
        since_hogql = since.strftime('%Y-%m-%d %H:%M:%S')
        until_hogql = until.strftime('%Y-%m-%d %H:%M:%S')

        logger.info(
            f"Starting session iteration: {since.isoformat()} to {until.isoformat()}, "
            f"page_size={page_size}"
        )

        # Build WHERE clause
        where_parts = [
            f"$start_timestamp >= toDateTime('{since_hogql}')",
            f"$start_timestamp < toDateTime('{until_hogql}')"
        ]

        # Add SEEK pagination if resuming
        if last_start_timestamp and last_session_id:
            last_ts_clean = last_start_timestamp[:19] if len(last_start_timestamp) > 19 else last_start_timestamp
            where_parts.append(
                f"($start_timestamp > toDateTime('{last_ts_clean}') OR "
                f"($start_timestamp = toDateTime('{last_ts_clean}') AND session_id > '{last_session_id}'))"
            )

        where_clause = " AND ".join(where_parts)

        # Sessions table has 43 columns - use SELECT *
        query = (
            f"SELECT * "  # nosec B608
            f"FROM sessions "
            f"WHERE {where_clause} "
            f"ORDER BY $start_timestamp ASC, session_id ASC "
            f"LIMIT {page_size}"
        )

        page_num = 0
        total_yielded = 0

        while True:
            try:
                logger.debug(f"Fetching sessions page {page_num + 1}...")
                result = self.execute_hogql_query(query)

                rows = result.get("results", [])
                columns = result.get("columns", [])

                if not rows:
                    logger.info(f"Session iteration complete. Total yielded: {total_yielded}")
                    break

                logger.debug(f"Page {page_num + 1}: {len(rows)} rows")

                # Convert list rows to dicts
                for row in rows:
                    session_dict = dict(zip(columns, row))
                    yield session_dict
                    total_yielded += 1

                if len(rows) < page_size:
                    logger.info(f"Final page. Total yielded: {total_yielded}")
                    break

                # Update SEEK parameters for next page
                last_row = rows[-1]
                last_row_dict = dict(zip(columns, last_row))
                last_start_timestamp = last_row_dict.get("$start_timestamp")
                last_session_id = last_row_dict.get("session_id")

                # Format timestamp
                last_ts_clean = last_start_timestamp[:19] if last_start_timestamp and len(last_start_timestamp) > 19 else last_start_timestamp

                where_parts_updated = [
                    f"$start_timestamp >= toDateTime('{since_hogql}')",
                    f"$start_timestamp < toDateTime('{until_hogql}')"
                ]

                if last_ts_clean:
                    where_parts_updated.append(
                        f"($start_timestamp > toDateTime('{last_ts_clean}') OR "
                        f"($start_timestamp = toDateTime('{last_ts_clean}') AND session_id > '{last_session_id}'))"
                    )

                where_clause = " AND ".join(where_parts_updated)
                query = (
                    f"SELECT * "  # nosec B608
                    f"FROM sessions "
                    f"WHERE {where_clause} "
                    f"ORDER BY $start_timestamp ASC, session_id ASC "
                    f"LIMIT {page_size}"
                )

                page_num += 1

            except PostHogRateLimitError as e:
                logger.error(f"Rate limit hit during session iteration: {e}")
                raise

    def iterate_person_distinct_ids(
        self,
        page_size: int = 1000
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate through person_distinct_ids (full table scan, no time filter)

        This table is typically small and maps distinct_id to person_id.
        No timestamp field available, so we can't do incremental loading.

        Args:
            page_size: Rows per page (100-10000)

        Yields:
            Individual mapping dicts with distinct_id and person_id

        Raises:
            PostHogAuthenticationError: If auth fails
            PostHogRateLimitError: If rate limited
            PostHogClientError: On other errors
        """
        logger.info(f"Starting person_distinct_ids iteration (full table): page_size={page_size}")

        # Simple offset pagination (no timestamp for SEEK)
        offset = 0

        while True:
            try:
                query = (
                    f"SELECT distinct_id, person_id "  # nosec B608
                    f"FROM person_distinct_ids "
                    f"LIMIT {page_size} OFFSET {offset}"
                )

                logger.debug(f"Fetching person_distinct_ids offset={offset}...")
                result = self.execute_hogql_query(query)

                rows = result.get("results", [])
                columns = result.get("columns", [])

                if not rows:
                    logger.info(f"person_distinct_ids iteration complete. Total offset: {offset}")
                    break

                logger.debug(f"Offset {offset}: {len(rows)} rows")

                # Convert list rows to dicts
                for row in rows:
                    mapping_dict = dict(zip(columns, row))
                    yield mapping_dict

                if len(rows) < page_size:
                    logger.info(f"Final page. Total rows: {offset + len(rows)}")
                    break

                offset += len(rows)

            except PostHogRateLimitError as e:
                logger.error(f"Rate limit hit during person_distinct_ids iteration: {e}")
                raise

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _get_retry_after(self, response: requests.Response) -> int:
        """
        Extract Retry-After header value

        Args:
            response: Response object

        Returns:
            Seconds to wait (default 1)
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                # Might be HTTP date format, default to 1
                return 1
        return 1

    def _check_rate_limit(self) -> None:
        """
        Check if we're approaching the hourly rate limit

        Removes timestamps older than 1 hour and pauses if we're
        approaching the 2,400 requests/hour limit
        """
        now = time.time()
        one_hour_ago = now - 3600

        # Remove old request times
        self._request_times = [t for t in self._request_times if t > one_hour_ago]

        # If approaching limit, sleep before next request
        threshold = self.RATE_LIMIT_PER_HOUR * 0.9  # 90% of limit
        if len(self._request_times) > threshold:
            sleep_time = 0.1  # Sleep 100ms between requests
            logger.warning(
                f"Approaching rate limit ({len(self._request_times)}/{self.RATE_LIMIT_PER_HOUR}). "
                f"Sleeping {sleep_time}s..."
            )
            time.sleep(sleep_time)

    def _to_iso_string(self, dt: datetime) -> str:
        """
        Convert datetime to ISO 8601 string

        Ensures timezone awareness (uses UTC if naive)

        Args:
            dt: Datetime object

        Returns:
            ISO 8601 string (e.g., "2025-11-08T10:30:00Z")
        """
        if dt.tzinfo is None:
            # Assume UTC if naive
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
