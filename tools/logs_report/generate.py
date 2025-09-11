#!/usr/bin/env python3
"""Enhanced HTML generator with comprehensive session details for developers."""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from osiris.core.session_reader import SessionReader


def classify_session_type(session_id: str) -> str:
    """Classify session by type based on ID pattern."""
    if "chat" in session_id:
        return "chat"
    elif "compile" in session_id:
        return "compile"
    elif "connections" in session_id or "connection" in session_id:
        return "connections"
    elif "ephemeral" in session_id:
        return "ephemeral"
    elif "run" in session_id:
        return "run"
    elif "test" in session_id or "validation" in session_id:
        return "test"
    else:
        return "other"


def is_e2b_session(logs_dir: str, session_id: str) -> bool:
    """Check if session was run with E2B remote execution."""
    session_path = Path(logs_dir) / session_id

    # Check metadata for remote execution
    metadata_file = session_path / "metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
                if "remote" in metadata:
                    return True
        except (OSError, json.JSONDecodeError):
            pass

    # Check events for E2B-specific events
    events_file = session_path / "events.jsonl"
    if events_file.exists():
        try:
            with open(events_file) as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_name = event.get("event", "")
                        if event_name.startswith("e2b."):
                            return True
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    return False


def get_pipeline_name(logs_dir: str, session_id: str) -> Optional[str]:
    """Extract pipeline name from session manifest or OML."""
    session_path = Path(logs_dir) / session_id

    # Try manifest.json in build/e2b or build directories
    for manifest_path in [
        session_path / "build" / "e2b" / "manifest.json",
        session_path / "build" / "manifest.json",
        session_path / "artifacts" / "manifest.json",
    ]:
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                    # Look for pipeline.id in manifest
                    if "pipeline" in manifest and "id" in manifest["pipeline"]:
                        return manifest["pipeline"]["id"]
            except (OSError, json.JSONDecodeError):
                continue

    # Try OML file if exists
    oml_file = session_path / "artifacts" / "generated_pipeline.yaml"
    if oml_file.exists():
        try:
            import yaml

            with open(oml_file) as f:
                oml = yaml.safe_load(f)
                if oml and "name" in oml:
                    return oml["name"]
        except Exception:  # nosec B110
            pass  # Safe to ignore YAML errors for non-critical display

    return None


def get_session_metadata(logs_dir: str, session_id: str) -> Dict[str, Any]:
    """Get session metadata including remote execution details."""
    session_path = Path(logs_dir) / session_id
    metadata_file = session_path / "metadata.json"

    if metadata_file.exists():
        try:
            with open(metadata_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    return {}


def get_pipeline_steps(logs_dir: str, session_id: str) -> list:
    """Extract pipeline steps from manifest for visualization."""
    session_path = Path(logs_dir) / session_id

    # Try manifest.json in build/e2b or build directories
    for manifest_path in [
        session_path / "build" / "e2b" / "manifest.json",
        session_path / "build" / "manifest.json",
    ]:
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                    if "steps" in manifest:
                        return manifest["steps"]
            except (OSError, json.JSONDecodeError):
                continue

    return []


def read_session_logs(logs_dir: str, session_id: str) -> Dict[str, Any]:
    """Read full session logs including events and metrics."""
    session_path = Path(logs_dir) / session_id
    result = {"events": [], "metrics": [], "artifacts": []}

    # Read events
    events_file = session_path / "events.jsonl"
    if events_file.exists():
        with open(events_file) as f:
            for line in f:
                try:
                    result["events"].append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

    # Read metrics
    metrics_file = session_path / "metrics.jsonl"
    if metrics_file.exists():
        with open(metrics_file) as f:
            for line in f:
                try:
                    result["metrics"].append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

    # List artifacts
    artifacts_dir = session_path / "artifacts"
    if artifacts_dir.exists():
        for item in artifacts_dir.iterdir():
            result["artifacts"].append(
                {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )

    # List artifacts and files in the session directory
    artifacts = []
    for item in session_path.iterdir():
        if item.is_file():
            size = item.stat().st_size
            artifacts.append(
                {
                    "name": item.name,
                    "type": "file",
                    "size": size,
                    "path": str(item.relative_to(session_path)),
                }
            )
        elif item.is_dir():
            # Recursively list directory contents
            dir_artifacts = []
            for root, _dirs, files in os.walk(item):
                root_path = Path(root)
                for file in files:
                    file_path = root_path / file
                    size = file_path.stat().st_size
                    rel_path = file_path.relative_to(session_path)
                    dir_artifacts.append(
                        {"name": str(rel_path), "type": "file", "size": size, "path": str(rel_path)}
                    )
            artifacts.append(
                {
                    "name": item.name,
                    "type": "directory",
                    "children": dir_artifacts,
                    "path": str(item.relative_to(session_path)),
                }
            )

    result["artifacts"] = artifacts

    # Read log files for Technical Logs tab
    logs = {}

    # Read osiris.log if it exists
    osiris_log = session_path / "osiris.log"
    if osiris_log.exists():
        try:
            with open(osiris_log) as f:
                logs["osiris.log"] = f.read()
        except Exception:
            logs["osiris.log"] = "Error reading osiris.log"

    # Read debug.log if it exists
    debug_log = session_path / "debug.log"
    if debug_log.exists():
        try:
            with open(debug_log) as f:
                logs["debug.log"] = f.read()
        except Exception:
            logs["debug.log"] = "Error reading debug.log"

    result["logs"] = logs
    return result


def generate_html_report(
    logs_dir: str = "./logs",
    output_dir: str = "dist/logs",
    status_filter: Optional[str] = None,
    label_filter: Optional[str] = None,
    since_filter: Optional[str] = None,
    limit: Optional[int] = None,
) -> None:
    """Generate static HTML report with overview page and individual session pages."""
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load sessions using SessionReader
    reader = SessionReader(logs_dir)
    sessions = reader.list_sessions()

    # Apply filters
    filtered_sessions = []
    for session in sessions:
        # Status filter
        if status_filter and session.status != status_filter:
            continue

        # Label filter
        if label_filter and label_filter not in session.labels:
            continue

        # Since filter
        if since_filter and session.started_at:
            try:
                from datetime import datetime

                since_dt = datetime.fromisoformat(since_filter.replace("Z", "+00:00"))
                session_dt = datetime.fromisoformat(session.started_at.replace("Z", "+00:00"))
                if session_dt < since_dt:
                    continue
            except (ValueError, AttributeError):
                pass

        filtered_sessions.append(session)

    # Apply limit
    if limit:
        filtered_sessions = filtered_sessions[:limit]

    # Generate main overview HTML page
    overview_html = generate_overview_page(filtered_sessions, logs_dir)
    (output_path / "index.html").write_text(overview_html)

    # Generate individual session detail pages
    for session in filtered_sessions:
        # Create session directory
        session_dir = output_path / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Read session logs and generate detail page
        session_logs = read_session_logs(logs_dir, session.session_id)
        session_html = generate_session_detail_page(session, session_logs)

        # Write session HTML file
        (session_dir / "index.html").write_text(session_html)


def generate_overview_page(sessions, logs_dir: str) -> str:
    """Generate the overview HTML page that lists all sessions."""
    # Group sessions by type
    session_groups = {"run": [], "compile": [], "connections": [], "ephemeral": [], "other": []}

    for session in sessions:
        session_type = classify_session_type(session.session_id)
        if session_type in session_groups:
            session_groups[session_type].append(session)
        else:
            session_groups["other"].append(session)

    # Generate simple HTML overview
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Osiris Session Logs</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 2rem;
            background: #fafafa;
        }}
        .header {{
            margin-bottom: 2rem;
            border-bottom: 1px solid #e5e5e5;
            padding-bottom: 1rem;
        }}
        h1 {{
            margin: 0 0 0.5rem 0;
            color: #1a1a1a;
        }}
        .subtitle {{
            color: #666;
            margin: 0;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: white;
            padding: 1rem;
            border-radius: 4px;
            border: 1px solid #e5e5e5;
        }}
        .stat-value {{
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 0.25rem;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.875rem;
        }}
        .section {{
            background: white;
            margin-bottom: 1.5rem;
            border-radius: 4px;
            border: 1px solid #e5e5e5;
            overflow: hidden;
        }}
        .section-header {{
            background: #f8f9fa;
            padding: 1rem;
            border-bottom: 1px solid #e5e5e5;
            font-weight: 600;
        }}
        .table-wrapper {{
            max-height: 600px;
            overflow-y: auto;
            position: relative;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        thead {{
            position: sticky;
            top: 0;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
            z-index: 10;
        }}
        th {{
            padding: 0.75rem 1rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.875rem;
            color: #495057;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        th.align-right {{
            text-align: right;
        }}
        tbody tr {{
            border-bottom: 1px solid #f0f0f0;
            transition: background-color 0.15s ease;
        }}
        tbody tr:hover {{
            background: #f8f9fa;
        }}
        tbody tr:last-child {{
            border-bottom: none;
        }}
        td {{
            padding: 0.75rem 1rem;
            font-size: 0.875rem;
        }}
        td.session-id {{
            font-family: monospace;
        }}
        td.session-time {{
            color: #666;
        }}
        td.session-duration {{
            color: #666;
            text-align: right;
        }}
        td.session-rows {{
            text-align: right;
            color: #666;
        }}
        .clickable-row {{
            cursor: pointer;
        }}
        th.sortable {{
            cursor: pointer;
            user-select: none;
            position: relative;
            padding-right: 1.5rem;
        }}
        th.sortable:hover {{
            background: #e9ecef;
        }}
        th.sortable::after {{
            content: '⇅';
            position: absolute;
            right: 0.5rem;
            opacity: 0.3;
        }}
        th.sortable.sort-asc::after {{
            content: '↑';
            opacity: 1;
        }}
        th.sortable.sort-desc::after {{
            content: '↓';
            opacity: 1;
        }}
        .session-status {{
            padding: 0.25rem 0.5rem;
            border-radius: 3px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status-success {{ background: #d4edda; color: #155724; }}
        .status-failed {{ background: #f8d7da; color: #721c24; }}
        .status-running {{ background: #fff3cd; color: #856404; }}
        .status-unknown {{ background: #e2e3e5; color: #383d41; }}
        .e2b-badge {{
            display: inline-block;
            background: #ff8c00;
            color: white;
            font-size: 0.75rem;
            font-weight: bold;
            padding: 0.2rem 0.5rem;
            border-radius: 3px;
            margin-left: 0.5rem;
        }}
        .search-bar {{
            background: white;
            padding: 1rem;
            margin-bottom: 1.5rem;
            border-radius: 4px;
            border: 1px solid #e5e5e5;
        }}
        .search-input {{
            width: 100%;
            padding: 0.5rem;
            font-size: 1rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: inherit;
        }}
        .search-input:focus {{
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25);
        }}
        .hidden {{
            display: none !important;
        }}
        .no-results {{
            text-align: center;
            padding: 2rem;
            color: #666;
        }}
        .pipeline-name {{
            color: #666;
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Osiris Session Logs</h1>
        <p class="subtitle">Pipeline execution logs and session details</p>
    </div>

    <div class="search-bar">
        <input type="text"
               class="search-input"
               id="searchInput"
               placeholder="Search sessions by ID, pipeline name, or status..."
               onkeyup="filterSessions()"
               autocomplete="off">
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{len(sessions)}</div>
            <div class="stat-label">Total Sessions</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{len([s for s in sessions if s.status == 'success'])}</div>
            <div class="stat-label">Successful</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{len([s for s in sessions if s.status == 'failed'])}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{sum(s.rows_out or 0 for s in sessions):,}</div>
            <div class="stat-label">Total Rows Processed</div>
        </div>
    </div>
"""

    # Add sections for each session type
    for session_type, type_sessions in session_groups.items():
        if not type_sessions:
            continue

        html += f"""
    <div class="section">
        <div class="section-header">{session_type.title()} Sessions ({len(type_sessions)})</div>
        <div class="table-wrapper">
            <table class="sortable-table" id="table-{session_type}">
                <thead>
                    <tr>
                        <th class="sortable" data-column="0" onclick="sortTable('table-{session_type}', 0)">Session ID</th>
                        <th class="sortable" data-column="1" onclick="sortTable('table-{session_type}', 1)">Pipeline</th>
                        <th class="sortable" data-column="2" onclick="sortTable('table-{session_type}', 2)">Started</th>
                        <th class="sortable align-right" data-column="3" onclick="sortTable('table-{session_type}', 3)">Duration</th>
                        <th class="sortable align-right" data-column="4" onclick="sortTable('table-{session_type}', 4)">Rows</th>
                        <th class="sortable" data-column="5" onclick="sortTable('table-{session_type}', 5)">Status</th>
                    </tr>
                </thead>
                <tbody>
"""

        for session in type_sessions:
            started_time = ""
            if session.started_at:
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(session.started_at.replace("Z", "+00:00"))
                    started_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, AttributeError):
                    started_time = session.started_at[:19].replace("T", " ")

            # Format duration
            duration = ""
            if session.duration_ms:
                if session.duration_ms < 1000:
                    duration = f"{session.duration_ms}ms"
                elif session.duration_ms < 60000:
                    duration = f"{session.duration_ms / 1000:.1f}s"
                else:
                    duration = f"{session.duration_ms / 60000:.1f}m"

            # Check if this session used E2B remote execution
            e2b_badge = ""
            if is_e2b_session(logs_dir, session.session_id):
                e2b_badge = '<span class="e2b-badge">E2B</span>'

            # Get pipeline name
            pipeline_name = get_pipeline_name(logs_dir, session.session_id) or ""

            # Get row count
            rows = session.rows_out if session.rows_out else 0
            rows_display = f"{rows:,}" if rows > 0 else "-"

            # Add data attributes for sorting
            duration_ms = session.duration_ms if session.duration_ms else 0

            html += f"""
                    <tr class="clickable-row" onclick="window.location.href='{session.session_id}/index.html'" data-duration="{duration_ms}" data-rows="{rows}" data-pipeline="{pipeline_name.lower()}">
                        <td class="session-id">{session.session_id}{e2b_badge}</td>
                        <td class="pipeline-name">{pipeline_name[:40] if pipeline_name else '-'}</td>
                        <td class="session-time">{started_time}</td>
                        <td class="session-duration">{duration or '-'}</td>
                        <td class="session-rows">{rows_display}</td>
                        <td><span class="session-status status-{session.status}">{session.status}</span></td>
                    </tr>
"""

        html += """
                </tbody>
            </table>
        </div>
    </div>
"""

    html += """
    <script>
        const sortStates = {};

        function sortTable(tableId, columnIndex) {
            const table = document.getElementById(tableId);
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const th = table.querySelectorAll('th')[columnIndex];

            // Get current sort state
            const key = tableId + '-' + columnIndex;
            const currentState = sortStates[key] || 'none';
            let newState = currentState === 'none' ? 'asc' :
                           currentState === 'asc' ? 'desc' : 'asc';

            // Clear all sort indicators for this table
            table.querySelectorAll('th').forEach(header => {
                header.classList.remove('sort-asc', 'sort-desc');
            });

            // Sort rows
            rows.sort((a, b) => {
                const cellA = a.cells[columnIndex];
                const cellB = b.cells[columnIndex];
                let valA = cellA.textContent.trim();
                let valB = cellB.textContent.trim();

                // Handle different data types
                if (columnIndex === 2) { // Duration column
                    // Convert to milliseconds for comparison
                    valA = parseDuration(valA);
                    valB = parseDuration(valB);
                } else if (columnIndex === 3) { // Rows column
                    valA = valA === '-' ? -1 : parseInt(valA.replace(/,/g, ''));
                    valB = valB === '-' ? -1 : parseInt(valB.replace(/,/g, ''));
                } else if (columnIndex === 1) { // Date column
                    valA = new Date(valA).getTime() || 0;
                    valB = new Date(valB).getTime() || 0;
                }

                // Compare
                let comparison = 0;
                if (typeof valA === 'number' && typeof valB === 'number') {
                    comparison = valA - valB;
                } else {
                    comparison = valA.toString().localeCompare(valB.toString());
                }

                return newState === 'asc' ? comparison : -comparison;
            });

            // Update DOM
            tbody.innerHTML = '';
            rows.forEach(row => tbody.appendChild(row));

            // Update sort indicator
            th.classList.add('sort-' + newState);
            sortStates[key] = newState;
        }

        function parseDuration(duration) {
            if (duration === '-') return -1;
            if (duration.endsWith('ms')) {
                return parseFloat(duration);
            } else if (duration.endsWith('s')) {
                return parseFloat(duration) * 1000;
            } else if (duration.endsWith('m')) {
                return parseFloat(duration) * 60000;
            }
            return 0;
        }

        function filterSessions() {
            const searchText = document.getElementById('searchInput').value.toLowerCase();
            const allSections = document.querySelectorAll('.section');
            let anyVisible = false;

            allSections.forEach(section => {
                const tbody = section.querySelector('tbody');
                if (!tbody) return;

                const rows = tbody.querySelectorAll('tr');
                let sectionHasVisibleRows = false;

                rows.forEach(row => {
                    const sessionId = row.querySelector('.session-id')?.textContent.toLowerCase() || '';
                    const pipelineName = row.querySelector('.pipeline-name')?.textContent.toLowerCase() || '';
                    const status = row.querySelector('.session-status')?.textContent.toLowerCase() || '';
                    const searchableText = sessionId + ' ' + pipelineName + ' ' + status;

                    if (searchableText.includes(searchText)) {
                        row.classList.remove('hidden');
                        sectionHasVisibleRows = true;
                        anyVisible = true;
                    } else {
                        row.classList.add('hidden');
                    }
                });

                // Hide/show entire section based on visible rows
                if (sectionHasVisibleRows) {
                    section.classList.remove('hidden');
                } else {
                    section.classList.add('hidden');
                }
            });

            // Show no results message if needed
            let noResultsDiv = document.getElementById('noResults');
            if (!anyVisible && searchText) {
                if (!noResultsDiv) {
                    noResultsDiv = document.createElement('div');
                    noResultsDiv.id = 'noResults';
                    noResultsDiv.className = 'section no-results';
                    noResultsDiv.innerHTML = '<p>No sessions found matching "' + searchText + '"</p>';
                    document.querySelector('.stats').insertAdjacentElement('afterend', noResultsDiv);
                } else {
                    noResultsDiv.innerHTML = '<p>No sessions found matching "' + searchText + '"</p>';
                    noResultsDiv.classList.remove('hidden');
                }
            } else if (noResultsDiv) {
                noResultsDiv.classList.add('hidden');
            }
        }
    </script>
</body>
</html>
"""

    return html


def generate_session_detail_page(session, session_logs) -> str:
    """Generate detailed session page with events, metrics, and artifacts."""
    events = session_logs.get("events", [])
    metrics = session_logs.get("metrics", [])
    artifacts = session_logs.get("artifacts", [])
    logs = session_logs.get("logs", {})

    # Get additional data from session directory
    import os

    logs_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "testing_env" in logs_dir:
        logs_dir = os.path.join(logs_dir, "testing_env", "logs")
    else:
        logs_dir = "./logs"

    metadata = get_session_metadata(logs_dir, session.session_id)
    pipeline_steps = get_pipeline_steps(logs_dir, session.session_id)

    # Parse events and metrics for display
    events_html = ""
    for event in events[:50]:  # Limit to first 50 events
        # Extract event data - events.jsonl has different structure
        timestamp = event.get("ts", event.get("timestamp", ""))
        event_name = event.get("event", "unknown")
        # session_id = event.get("session", event.get("session_id", ""))  # Not used

        # Format timestamp for display
        display_time = ""
        if timestamp:
            try:
                from datetime import datetime

                if "T" in timestamp:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    display_time = dt.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
                else:
                    display_time = timestamp
            except (ValueError, AttributeError):
                display_time = timestamp[:19] if len(timestamp) > 19 else timestamp

        # Create event message with details
        event_details = []
        for key, value in event.items():
            if key not in ["ts", "timestamp", "event", "session", "session_id"]:
                if isinstance(value, (int, float)) and key.endswith(("_ms", "duration")):
                    # Format durations nicely
                    if value < 1:
                        event_details.append(f"{key}={value*1000:.1f}ms")
                    else:
                        event_details.append(f"{key}={value:.2f}s")
                else:
                    event_details.append(f"{key}={value}")

        detail_str = " | " + " | ".join(event_details) if event_details else ""

        # Determine event type for styling
        event_class = "info"
        if "error" in event_name.lower() or "fail" in event_name.lower():
            event_class = "error"
        elif "warn" in event_name.lower():
            event_class = "warning"
        elif event_name.startswith("e2b."):
            event_class = "e2b"

        events_html += f"""
        <div class="log-entry log-{event_class}">
            <span class="timestamp">{display_time}</span>
            <span class="level event-{event_class}">{event_name}</span>
            <span class="message">{detail_str}</span>
        </div>
        """

    metrics_html = ""
    for metric in metrics[:20]:  # Limit to first 20 metrics
        # Extract metric data - metrics.jsonl has ts, metric, value, unit structure
        timestamp = metric.get("ts", metric.get("timestamp", ""))
        metric_name = metric.get("metric", metric.get("name", "unknown"))
        value = metric.get("value", "")
        unit = metric.get("unit", "")

        # Format timestamp for display
        display_time = ""
        if timestamp:
            try:
                from datetime import datetime

                if "T" in timestamp:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    display_time = dt.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
                else:
                    display_time = timestamp
            except (ValueError, AttributeError):
                display_time = timestamp[:19] if len(timestamp) > 19 else timestamp

        # Format value with unit
        formatted_value = str(value)
        if isinstance(value, (int, float)):
            if unit == "bytes":
                # Format bytes nicely
                if value >= 1024 * 1024:
                    formatted_value = f"{value/(1024*1024):.1f}MB"
                elif value >= 1024:
                    formatted_value = f"{value/1024:.1f}KB"
                else:
                    formatted_value = f"{value} bytes"
            elif unit == "seconds":
                # Format durations nicely
                formatted_value = f"{value*1000:.1f}ms" if value < 1 else f"{value:.2f}s"
            else:
                # Regular number with unit
                if isinstance(value, float):
                    formatted_value = f"{value:.3f}"
                formatted_value += f" {unit}" if unit else ""

        # Color code metrics by type
        metric_class = "default"
        if "duration" in metric_name or "time" in metric_name:
            metric_class = "duration"
        elif "size" in metric_name or "bytes" in metric_name:
            metric_class = "size"
        elif "error" in metric_name:
            metric_class = "error"
        elif "e2b" in metric_name:
            metric_class = "e2b"

        metrics_html += f"""
        <div class="metric-entry metric-{metric_class}">
            <span class="timestamp">{display_time}</span>
            <span class="name">{metric_name}</span>
            <span class="value">{formatted_value}</span>
        </div>
        """

    # Generate artifacts HTML
    artifacts_html = ""
    if artifacts:
        artifacts_html = '<div class="artifact-tree">'
        for artifact in sorted(artifacts, key=lambda x: (x["type"] != "directory", x["name"])):
            if artifact["type"] == "file":
                # Format file size
                size = artifact.get("size", 0)
                if size >= 1024 * 1024:
                    size_str = f"{size/(1024*1024):.1f} MB"
                elif size >= 1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size} bytes"

                # Special handling for certain file types
                icon = "📄"
                if artifact["name"].endswith(".log"):
                    icon = "📋"
                elif artifact["name"].endswith(".json") or artifact["name"].endswith(".jsonl"):
                    icon = "📊"
                elif artifact["name"].endswith(".yaml") or artifact["name"].endswith(".yml"):
                    icon = "📝"
                elif artifact["name"].endswith(".csv"):
                    icon = "📈"

                artifacts_html += f"""
                <div class="artifact-item artifact-file">
                    <span class="artifact-icon">{icon}</span>
                    <span class="artifact-name">{artifact['name']}</span>
                    <span class="artifact-size">{size_str}</span>
                </div>
                """
            elif artifact["type"] == "directory":
                # Directory with children
                artifacts_html += f"""
                <div class="artifact-item artifact-directory">
                    <span class="artifact-icon">📁</span>
                    <span class="artifact-name">{artifact['name']}/</span>
                    <span class="artifact-size">{len(artifact.get('children', []))} items</span>
                </div>
                """
                # Show children indented
                for child in sorted(artifact.get("children", []), key=lambda x: x["name"]):
                    size = child.get("size", 0)
                    if size >= 1024 * 1024:
                        size_str = f"{size/(1024*1024):.1f} MB"
                    elif size >= 1024:
                        size_str = f"{size/1024:.1f} KB"
                    else:
                        size_str = f"{size} bytes"

                    artifacts_html += f"""
                    <div class="artifact-item artifact-file artifact-child">
                        <span class="artifact-icon">📄</span>
                        <span class="artifact-name">{child['name']}</span>
                        <span class="artifact-size">{size_str}</span>
                    </div>
                    """
        artifacts_html += "</div>"
    else:
        artifacts_html = '<div class="empty-state">No artifacts found for this session</div>'

    # Generate Technical Logs HTML
    logs_html = ""
    if logs:
        # Create sub-tabs for different log files
        log_tabs = []
        log_panels = []

        for idx, (log_name, log_content) in enumerate(logs.items()):
            active_class = "active" if idx == 0 else ""
            log_tabs.append(
                f'<div class="log-tab {active_class}" onclick="showLogTab(\'{log_name}\')">{log_name}</div>'
            )

            # Format log content with syntax highlighting for common patterns
            formatted_content = log_content.replace("<", "&lt;").replace(">", "&gt;")

            # Simple syntax highlighting
            # Highlight timestamps
            formatted_content = re.sub(
                r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\.\d]*)",
                r'<span class="log-timestamp">\1</span>',
                formatted_content,
            )
            # Highlight log levels
            formatted_content = re.sub(
                r"\b(ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL)\b",
                lambda m: f'<span class="log-{m.group(1).lower()}">{m.group(1)}</span>',
                formatted_content,
            )
            # Highlight file paths
            formatted_content = re.sub(
                r"([/\w\-\.]+\.(py|yaml|json|log))",
                r'<span class="log-path">\1</span>',
                formatted_content,
            )

            log_panels.append(
                f"""
                <div id="log-{log_name}" class="log-panel {active_class}">
                    <pre class="log-content">{formatted_content}</pre>
                </div>
            """
            )

        logs_html = f"""
            <div class="log-tabs">
                {''.join(log_tabs)}
            </div>
            <div class="log-panels">
                {''.join(log_panels)}
            </div>
        """
    else:
        logs_html = '<div class="empty-state">No log files found for this session</div>'

    # Generate Metadata HTML
    metadata_html = "<div class='metadata-grid'>"
    if metadata:
        # Remote execution metadata
        if "remote" in metadata:
            remote = metadata["remote"]
            metadata_html += """<div class='metadata-section'>
                <h3>Remote Execution (E2B)</h3>
                <div class='metadata-entries'>"""

            if "payload" in remote:
                payload = remote["payload"]
                metadata_html += f"""<div class='metadata-entry'>
                    <span class='metadata-key'>Payload Size:</span>
                    <span class='metadata-value'>{payload.get('total_size_bytes', 0):,} bytes</span>
                </div>"""
                metadata_html += f"""<div class='metadata-entry'>
                    <span class='metadata-key'>SHA256:</span>
                    <span class='metadata-value'>{payload.get('sha256', 'N/A')[:12]}...</span>
                </div>"""

                if "files" in payload:
                    metadata_html += (
                        """<div class='metadata-entry'>
                        <span class='metadata-key'>Files:</span>
                        <span class='metadata-value'>"""
                        + ", ".join([f["name"] for f in payload["files"]])
                        + """</span>
                    </div>"""
                    )

            metadata_html += """</div></div>"""

        # Add any other metadata sections
        for key, value in metadata.items():
            if key != "remote" and isinstance(value, dict):
                metadata_html += f"""<div class='metadata-section'>
                    <h3>{key.replace('_', ' ').title()}</h3>
                    <div class='metadata-entries'>"""

                for sub_key, sub_value in value.items():
                    metadata_html += f"""<div class='metadata-entry'>
                        <span class='metadata-key'>{sub_key.replace('_', ' ').title()}:</span>
                        <span class='metadata-value'>{sub_value}</span>
                    </div>"""

                metadata_html += """</div></div>"""
    else:
        metadata_html += '<div class="empty-state">No metadata available for this session</div>'
    metadata_html += "</div>"

    # Generate Pipeline Steps HTML with Mermaid diagram
    pipeline_steps_html = ""
    if pipeline_steps:
        # Create Mermaid diagram
        mermaid_nodes = []
        mermaid_edges = []

        for step in pipeline_steps:
            step_id = step.get("id", "unknown")
            driver = step.get("driver", "unknown")
            needs = step.get("needs", [])

            # Create node
            node_label = f"{step_id}\n[{driver}]"
            mermaid_nodes.append(f'    {step_id}["{node_label}"]')

            # Create edges
            for dep in needs:
                mermaid_edges.append(f"    {dep} --> {step_id}")

        # Build Mermaid diagram
        mermaid_diagram = "graph TD\n"
        if not mermaid_edges:
            # No dependencies, show all nodes linearly
            for i, node in enumerate(mermaid_nodes):
                mermaid_diagram += node + "\n"
                if i < len(mermaid_nodes) - 1:
                    step_id = pipeline_steps[i]["id"]
                    next_id = pipeline_steps[i + 1]["id"]
                    mermaid_diagram += f"    {step_id} --> {next_id}\n"
        else:
            mermaid_diagram += "\n".join(mermaid_nodes) + "\n"
            mermaid_diagram += "\n".join(mermaid_edges)

        pipeline_steps_html = f"""<div class='pipeline-visualization'>
            <h3>Pipeline Flow</h3>
            <div class='mermaid'>
                {mermaid_diagram}
            </div>
            <h3>Step Details</h3>
            <div class='steps-list'>"""

        for step in pipeline_steps:
            pipeline_steps_html += f"""<div class='step-detail'>
                <div class='step-header'>{step.get('id', 'unknown')}</div>
                <div class='step-info'>
                    <div>Driver: {step.get('driver', 'unknown')}</div>
                    <div>Config: {step.get('cfg_path', 'N/A')}</div>
                    <div>Dependencies: {', '.join(step.get('needs', [])) or 'None'}</div>
                </div>
            </div>"""

        pipeline_steps_html += """</div></div>
        <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
        <script>mermaid.initialize({startOnLoad:true});</script>"""
    else:
        pipeline_steps_html = (
            '<div class="empty-state">No pipeline steps information available</div>'
        )

    # Generate Performance Dashboard HTML
    performance_html = "<div class='performance-dashboard'>"

    # Group metrics by category
    duration_metrics = []
    size_metrics = []
    count_metrics = []
    e2b_metrics = []

    for metric in metrics:
        metric_name = metric.get("metric", "")
        if "duration" in metric_name or "time" in metric_name:
            duration_metrics.append(metric)
        elif "size" in metric_name or "bytes" in metric_name:
            size_metrics.append(metric)
        elif "count" in metric_name or "rows" in metric_name:
            count_metrics.append(metric)
        elif "e2b" in metric_name:
            e2b_metrics.append(metric)

    # Duration metrics
    if duration_metrics:
        performance_html += """<div class='perf-section'>
            <h3>⏱️ Timing Metrics</h3>
            <div class='perf-grid'>"""

        for metric in duration_metrics:
            value = metric.get("value", 0)
            unit = metric.get("unit", "")
            formatted_value = (
                f"{value*1000:.1f}ms"
                if unit == "seconds" and value < 1
                else f"{value:.2f}s" if unit == "seconds" else f"{value} {unit}"
            )

            performance_html += f"""<div class='perf-card'>
                <div class='perf-value'>{formatted_value}</div>
                <div class='perf-label'>{metric.get('metric', 'unknown')}</div>
            </div>"""

        performance_html += """</div></div>"""

    # Size metrics
    if size_metrics:
        performance_html += """<div class='perf-section'>
            <h3>💾 Data Size Metrics</h3>
            <div class='perf-grid'>"""

        for metric in size_metrics:
            value = metric.get("value", 0)
            unit = metric.get("unit", "")
            if unit == "bytes":
                if value >= 1024 * 1024:
                    formatted_value = f"{value/(1024*1024):.1f}MB"
                elif value >= 1024:
                    formatted_value = f"{value/1024:.1f}KB"
                else:
                    formatted_value = f"{value} bytes"
            else:
                formatted_value = f"{value} {unit}"

            performance_html += f"""<div class='perf-card'>
                <div class='perf-value'>{formatted_value}</div>
                <div class='perf-label'>{metric.get('metric', 'unknown')}</div>
            </div>"""

        performance_html += """</div></div>"""

    # E2B metrics
    if e2b_metrics:
        performance_html += """<div class='perf-section'>
            <h3>🚀 E2B Remote Execution</h3>
            <div class='perf-grid'>"""

        for metric in e2b_metrics:
            value = metric.get("value", 0)
            unit = metric.get("unit", "")
            formatted_value = str(value)

            if unit == "seconds":
                formatted_value = f"{value*1000:.1f}ms" if value < 1 else f"{value:.2f}s"
            elif unit == "bytes":
                formatted_value = f"{value / 1024:.1f}KB" if value >= 1024 else f"{value} bytes"
            elif unit:
                formatted_value = f"{value} {unit}"

            performance_html += f"""<div class='perf-card'>
                <div class='perf-value'>{formatted_value}</div>
                <div class='perf-label'>{metric.get('metric', 'unknown')}</div>
            </div>"""

        performance_html += """</div></div>"""

    if not (duration_metrics or size_metrics or e2b_metrics):
        performance_html += '<div class="empty-state">No performance metrics available</div>'

    performance_html += "</div>"

    # Format session duration
    duration = ""
    if session.duration_ms:
        if session.duration_ms < 1000:
            duration = f"{session.duration_ms}ms"
        elif session.duration_ms < 60000:
            duration = f"{session.duration_ms / 1000:.1f}s"
        else:
            duration = f"{session.duration_ms / 60000:.1f}m"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{session.session_id} - Osiris Session Detail</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 2rem;
            background: #fafafa;
        }}
        .header {{
            margin-bottom: 2rem;
            border-bottom: 1px solid #e5e5e5;
            padding-bottom: 1rem;
        }}
        h1 {{
            margin: 0 0 0.5rem 0;
            color: #1a1a1a;
            font-family: monospace;
        }}
        .subtitle {{
            color: #666;
            margin: 0;
        }}
        .back-link {{
            color: #0066cc;
            text-decoration: none;
            margin-bottom: 1rem;
            display: inline-block;
        }}
        .back-link:hover {{
            text-decoration: underline;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .info-card {{
            background: white;
            padding: 1rem;
            border-radius: 4px;
            border: 1px solid #e5e5e5;
        }}
        .info-label {{
            color: #666;
            font-size: 0.875rem;
            margin-bottom: 0.25rem;
        }}
        .info-value {{
            font-weight: 600;
        }}
        .tabs {{
            display: flex;
            background: white;
            border: 1px solid #e5e5e5;
            border-radius: 4px 4px 0 0;
            margin-bottom: 0;
        }}
        .tab {{
            padding: 1rem 1.5rem;
            cursor: pointer;
            border-right: 1px solid #e5e5e5;
            background: #f8f9fa;
        }}
        .tab.active {{
            background: white;
            border-bottom: 1px solid white;
            position: relative;
            z-index: 1;
        }}
        .tab:last-child {{
            border-right: none;
        }}
        .tab-content {{
            background: white;
            border: 1px solid #e5e5e5;
            border-top: none;
            border-radius: 0 0 4px 4px;
            padding: 1rem;
            max-height: 600px;
            overflow-y: auto;
        }}
        .tab-panel {{
            display: none;
        }}
        .tab-panel.active {{
            display: block;
        }}
        .log-entry {{
            display: grid;
            grid-template-columns: auto auto 1fr;
            gap: 1rem;
            padding: 0.5rem;
            border-bottom: 1px solid #f0f0f0;
            font-family: monospace;
            font-size: 0.875rem;
        }}
        .log-entry:hover {{
            background: #f8f9fa;
        }}
        .timestamp {{
            color: #666;
        }}
        .level {{
            font-weight: 600;
            text-transform: uppercase;
        }}
        .log-info .level {{
            color: #0066cc;
        }}
        .log-warning .level {{
            color: #ff8800;
        }}
        .log-error .level {{
            color: #cc0000;
        }}
        .message {{
            word-break: break-word;
        }}
        .metric-entry {{
            display: grid;
            grid-template-columns: auto auto 1fr;
            gap: 1rem;
            padding: 0.5rem;
            border-bottom: 1px solid #f0f0f0;
            font-family: monospace;
            font-size: 0.875rem;
        }}
        .metric-entry:hover {{
            background: #f8f9fa;
        }}
        .empty-state {{
            text-align: center;
            color: #666;
            padding: 2rem;
        }}
        .artifact-tree {{
            font-family: monospace;
            font-size: 0.875rem;
        }}
        .artifact-item {{
            display: grid;
            grid-template-columns: auto 1fr auto;
            gap: 0.5rem;
            padding: 0.4rem;
            border-bottom: 1px solid #f0f0f0;
        }}
        .artifact-item:hover {{
            background: #f8f9fa;
        }}
        .artifact-directory {{
            font-weight: 600;
            background: #f8f9fa;
        }}
        .artifact-child {{
            padding-left: 2rem;
        }}
        .artifact-icon {{
            width: 1.5rem;
        }}
        .artifact-name {{
            color: #333;
        }}
        .artifact-size {{
            color: #666;
            text-align: right;
        }}
        /* Technical Logs styles */
        .log-tabs {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            border-bottom: 2px solid #dee2e6;
        }}
        .log-tab {{
            padding: 0.5rem 1rem;
            cursor: pointer;
            background: #f8f9fa;
            border-radius: 4px 4px 0 0;
            font-weight: 600;
            font-size: 0.875rem;
        }}
        .log-tab.active {{
            background: white;
            border-bottom: 2px solid white;
            margin-bottom: -2px;
        }}
        .log-panel {{
            display: none;
        }}
        .log-panel.active {{
            display: block;
        }}
        .log-content {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.8rem;
            line-height: 1.4;
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 1rem;
            border-radius: 4px;
            overflow-x: auto;
            max-height: 600px;
            overflow-y: auto;
        }}
        .log-timestamp {{
            color: #9cdcfe;
        }}
        .log-error, .log-critical {{
            color: #f48771;
            font-weight: bold;
        }}
        .log-warn, .log-warning {{
            color: #dcdcaa;
            font-weight: bold;
        }}
        .log-info {{
            color: #4ec9b0;
        }}
        .log-debug {{
            color: #808080;
        }}
        .log-path {{
            color: #ce9178;
            text-decoration: underline;
        }}
        /* Metadata tab styles */
        .metadata-grid {{
            font-family: monospace;
            font-size: 0.875rem;
        }}
        .metadata-section {{
            margin-bottom: 1.5rem;
        }}
        .metadata-section h3 {{
            color: #333;
            margin-bottom: 0.5rem;
            font-size: 1rem;
            font-weight: 600;
        }}
        .metadata-entries {{
            background: #f8f9fa;
            padding: 0.75rem;
            border-radius: 4px;
        }}
        .metadata-entry {{
            display: grid;
            grid-template-columns: 200px 1fr;
            gap: 1rem;
            padding: 0.4rem 0;
            border-bottom: 1px solid #e9ecef;
        }}
        .metadata-entry:last-child {{
            border-bottom: none;
        }}
        .metadata-key {{
            font-weight: 600;
            color: #495057;
        }}
        .metadata-value {{
            color: #212529;
            word-break: break-all;
        }}
        /* Pipeline Steps styles */
        .pipeline-visualization {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .pipeline-visualization h3 {{
            color: #333;
            margin: 1rem 0;
            font-size: 1rem;
        }}
        .mermaid {{
            text-align: center;
            background: #f8f9fa;
            padding: 2rem;
            border-radius: 4px;
            margin-bottom: 2rem;
        }}
        .steps-list {{
            display: grid;
            gap: 0.75rem;
        }}
        .step-detail {{
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 0.75rem;
            font-family: monospace;
            font-size: 0.875rem;
        }}
        .step-header {{
            font-weight: 600;
            color: #0066cc;
            margin-bottom: 0.5rem;
        }}
        .step-info {{
            color: #666;
            line-height: 1.5;
        }}
        /* Performance Dashboard styles */
        .performance-dashboard {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .perf-section {{
            margin-bottom: 2rem;
        }}
        .perf-section h3 {{
            color: #333;
            margin-bottom: 1rem;
            font-size: 1rem;
            font-weight: 600;
        }}
        .perf-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
        }}
        .perf-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1rem;
            border-radius: 4px;
            text-align: center;
        }}
        .perf-value {{
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 0.25rem;
        }}
        .perf-label {{
            font-size: 0.75rem;
            opacity: 0.9;
            text-transform: uppercase;
        }}
    </style>
</head>
<body>
    <a href="../index.html" class="back-link">← Back to Sessions</a>

    <div class="header">
        <h1>{session.session_id}</h1>
        <p class="subtitle">Session details and execution logs</p>
    </div>

    <div class="info-grid">
        <div class="info-card">
            <div class="info-label">Status</div>
            <div class="info-value">{session.status}</div>
        </div>
        <div class="info-card">
            <div class="info-label">Started</div>
            <div class="info-value">{session.started_at[:19].replace('T', ' ') if session.started_at else 'N/A'}</div>
        </div>
        <div class="info-card">
            <div class="info-label">Duration</div>
            <div class="info-value">{duration or 'N/A'}</div>
        </div>
        <div class="info-card">
            <div class="info-label">Rows Processed</div>
            <div class="info-value">{session.rows_out or 0:,}</div>
        </div>
        <div class="info-card">
            <div class="info-label">Steps</div>
            <div class="info-value">{session.steps_ok or 0} / {session.steps_total or 0}</div>
        </div>
        <div class="info-card">
            <div class="info-label">Errors</div>
            <div class="info-value">{session.errors or 0}</div>
        </div>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="showTab('events')">Events ({len(events)})</div>
        <div class="tab" onclick="showTab('metrics')">Metrics ({len(metrics)})</div>
        <div class="tab" onclick="showTab('artifacts')">Artifacts ({len(artifacts)})</div>
        <div class="tab" onclick="showTab('logs')">Technical Logs</div>
        <div class="tab" onclick="showTab('metadata')">Metadata</div>
        <div class="tab" onclick="showTab('pipeline')">Pipeline Steps</div>
        <div class="tab" onclick="showTab('performance')">Performance</div>
        <div class="tab" onclick="showTab('overview')">Overview</div>
    </div>

    <div class="tab-content">
        <div id="events" class="tab-panel active">
            {events_html if events_html.strip() else '<div class="empty-state">No events recorded for this session</div>'}
        </div>
        <div id="metrics" class="tab-panel">
            {metrics_html if metrics_html.strip() else '<div class="empty-state">No metrics recorded for this session</div>'}
        </div>
        <div id="artifacts" class="tab-panel">
            {artifacts_html}
        </div>
        <div id="logs" class="tab-panel">
            {logs_html}
        </div>
        <div id="metadata" class="tab-panel">
            {metadata_html}
        </div>
        <div id="pipeline" class="tab-panel">
            {pipeline_steps_html}
        </div>
        <div id="performance" class="tab-panel">
            {performance_html}
        </div>
        <div id="overview" class="tab-panel">
            <div class="empty-state">Session overview coming soon</div>
        </div>
    </div>

    <script>
        function showTab(tabName) {{
            // Hide all tab panels
            document.querySelectorAll('.tab-panel').forEach(panel => {{
                panel.classList.remove('active');
            }});

            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {{
                tab.classList.remove('active');
            }});

            // Show selected tab panel
            document.getElementById(tabName).classList.add('active');

            // Add active class to clicked tab
            event.target.classList.add('active');
        }}

        function showLogTab(logName) {{
            // Hide all log panels
            document.querySelectorAll('.log-panel').forEach(panel => {{
                panel.classList.remove('active');
            }});

            // Remove active class from all log tabs
            document.querySelectorAll('.log-tab').forEach(tab => {{
                tab.classList.remove('active');
            }});

            // Show selected log panel
            document.getElementById('log-' + logName).classList.add('active');

            // Add active class to clicked log tab
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>
"""

    return html
