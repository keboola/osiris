#!/usr/bin/env python3
"""Enhanced HTML generator with comprehensive session details for developers."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from osiris.core.logs_serialize import to_index_json, to_session_json
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


def read_session_logs(logs_dir: str, session_id: str) -> dict[str, Any]:
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

    return result


def generate_html_report(
    logs_dir: str = "./logs",
    output_dir: str = "dist/logs",
    status_filter: str | None = None,
    label_filter: str | None = None,
    since_filter: str | None = None,
    limit: int | None = None,
) -> None:
    """Generate static HTML report from session logs with enhanced developer features."""
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

    # Generate JSON data
    index_json = to_index_json(filtered_sessions)
    (output_path / "data.json").write_text(index_json)

    # Generate detailed session JSON with full logs
    session_details = {}
    for session in filtered_sessions:
        session_json = to_session_json(session, logs_dir)
        session_data = json.loads(session_json)
        # Add full logs to session data
        session_logs = read_session_logs(logs_dir, session.session_id)
        session_data["logs"] = session_logs
        session_details[session.session_id] = session_data

    # Generate HTML with embedded data
    html_content = generate_index_html(index_json, session_details)
    (output_path / "index.html").write_text(html_content)


def generate_index_html(data_json: str, session_details: dict) -> str:
    """Generate the single-page HTML application with enhanced developer features."""

    # Parse and minify JSON
    data_obj = json.loads(data_json)
    minified_data = json.dumps(data_obj, separators=(",", ":"))
    minified_details = json.dumps(session_details, separators=(",", ":"))

    # Build HTML in parts to avoid escaping issues
    html_parts = []

    # Start of HTML with modern, clean design
    html_parts.append(
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Osiris Session Logs Browser</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #fafafa;
            --bg-secondary: #ffffff;
            --text-primary: #1a1a1a;
            --text-secondary: #666666;
            --text-muted: #999999;
            --border-color: #e5e5e5;
            --border-light: #f0f0f0;
            --accent-blue: #0066ff;
            --accent-green: #00cc88;
            --accent-yellow: #ffcc00;
            --accent-red: #ff3333;
            --accent-purple: #9333ea;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
            --font-mono: 'SF Mono', Monaco, 'Cascadia Code', 'Courier New', monospace;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        /* Header styles */
        .header {
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        h1 {
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.25rem;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1rem;
        }

        /* Stats cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .stat-card {
            background: var(--bg-secondary);
            padding: 1.25rem;
            border: 1px solid var(--border-light);
            border-radius: 4px;
            transition: all 0.2s ease;
        }

        .stat-card:hover {
            box-shadow: var(--shadow-md);
            border-color: var(--border-color);
        }

        .stat-value {
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }

        .stat-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }

        /* Filters section - more subtle */
        .filters-section {
            background: var(--bg-secondary);
            border: 1px solid var(--border-light);
            border-radius: 4px;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }

        .filters-header {
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            margin-bottom: 0.75rem;
        }

        .filters-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }

        .filter-group {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .filter-label {
            font-size: 0.75rem;
            font-weight: 500;
            color: var(--text-secondary);
        }

        input[type="text"], select {
            padding: 0.375rem 0.5rem;
            border: 1px solid var(--border-light);
            background: var(--bg-primary);
            font-size: 0.8rem;
            border-radius: 3px;
            transition: all 0.2s ease;
        }

        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: var(--accent-blue);
            background: var(--bg-secondary);
        }

        /* Session type filters - more compact */
        .type-filters {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            padding: 0.75rem 0;
            border-top: 1px solid var(--border-light);
            border-bottom: 1px solid var(--border-light);
            margin: 0.75rem 0;
        }

        .type-filter {
            display: flex;
            align-items: center;
            gap: 0.375rem;
            cursor: pointer;
            user-select: none;
        }

        .type-filter input[type="checkbox"] {
            width: 1rem;
            height: 1rem;
            cursor: pointer;
        }

        .type-filter label {
            font-size: 0.8rem;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }

        .type-badge {
            display: inline-block;
            padding: 0.125rem 0.375rem;
            font-size: 0.7rem;
            font-weight: 600;
            border-radius: 3px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .type-chat { background: #e3f2fd; color: #1565c0; }
        .type-compile { background: #f3e5f5; color: #7b1fa2; }
        .type-connections { background: #e8f5e9; color: #2e7d32; }
        .type-ephemeral { background: #fff3e0; color: #ef6c00; }
        .type-run { background: #e0f2f1; color: #00695c; }
        .type-test { background: #fce4ec; color: #c2185b; }
        .type-other { background: #f5f5f5; color: #616161; }

        /* Buttons */
        .btn {
            padding: 0.375rem 0.75rem;
            border: 1px solid var(--text-primary);
            background: var(--text-primary);
            color: var(--bg-secondary);
            font-size: 0.8rem;
            font-weight: 500;
            cursor: pointer;
            border-radius: 3px;
            transition: all 0.2s ease;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .btn:hover {
            background: transparent;
            color: var(--text-primary);
        }

        .btn-secondary {
            background: transparent;
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            border-color: var(--text-primary);
            background: var(--text-primary);
            color: var(--bg-secondary);
        }

        /* Timeline section */
        .timeline-section {
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-light);
            border-radius: 4px;
        }

        .timeline-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }

        .timeline-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--text-primary);
        }

        .timeline-help {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        #timeline {
            width: 100%;
            height: 100px;
            border: 1px solid var(--border-light);
            background: var(--bg-primary);
            border-radius: 3px;
            cursor: crosshair;
        }

        .timeline-tooltip {
            position: absolute;
            background: var(--text-primary);
            color: var(--bg-secondary);
            padding: 0.5rem;
            border-radius: 3px;
            font-size: 0.75rem;
            pointer-events: none;
            display: none;
            z-index: 1000;
            box-shadow: var(--shadow-md);
        }

        /* Table styles */
        .table-container {
            background: var(--bg-secondary);
            border: 1px solid var(--border-light);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 2rem;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            background: var(--bg-primary);
            padding: 0.75rem;
            text-align: left;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 0.75rem;
            border-bottom: 1px solid var(--border-light);
            font-size: 0.875rem;
        }

        tr:hover {
            background: var(--bg-primary);
        }

        /* Status badges */
        .status {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-radius: 3px;
        }

        .status-success {
            background: var(--accent-green);
            color: white;
        }

        .status-failed {
            background: var(--accent-red);
            color: white;
        }

        .status-running {
            background: var(--accent-yellow);
            color: black;
        }

        .status-unknown {
            background: var(--text-muted);
            color: white;
        }

        /* Clickable elements */
        .clickable {
            color: var(--accent-blue);
            cursor: pointer;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.2s ease;
        }

        .clickable:hover {
            text-decoration: underline;
        }

        /* Detail view */
        #detail-view {
            display: none;
        }

        #detail-view.active {
            display: block;
        }

        .detail-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        .detail-header h2 {
            font-size: 1.25rem;
            font-weight: 600;
            letter-spacing: -0.02em;
            flex: 1;
        }

        /* Tabbed interface for detail view */
        .tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
            border-bottom: 2px solid var(--border-light);
        }

        .tab {
            padding: 0.5rem 1rem;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: all 0.2s ease;
        }

        .tab:hover {
            color: var(--text-primary);
        }

        .tab.active {
            color: var(--accent-blue);
            border-bottom-color: var(--accent-blue);
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Metrics grid */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .metric-card {
            background: var(--bg-secondary);
            padding: 1rem;
            border: 1px solid var(--border-light);
            border-radius: 4px;
        }

        .metric-label {
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }

        .metric-value {
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }

        /* Events timeline */
        .events-timeline {
            max-height: 400px;
            overflow-y: auto;
            background: var(--bg-primary);
            border: 1px solid var(--border-light);
            border-radius: 4px;
            padding: 1rem;
        }

        .event-item {
            display: flex;
            gap: 1rem;
            padding: 0.5rem;
            border-bottom: 1px solid var(--border-light);
            font-size: 0.875rem;
        }

        .event-item:hover {
            background: var(--bg-secondary);
        }

        .event-time {
            color: var(--text-muted);
            font-family: var(--font-mono);
            font-size: 0.75rem;
            width: 80px;
        }

        .event-type {
            font-weight: 500;
            color: var(--text-primary);
            width: 150px;
        }

        .event-details {
            flex: 1;
            color: var(--text-secondary);
            font-family: var(--font-mono);
            font-size: 0.75rem;
        }

        /* Steps visualization */
        .steps-flow {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            margin: 1rem 0;
        }

        .step-item {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 0.75rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-light);
            border-radius: 4px;
        }

        .step-icon {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
        }

        .step-icon.success { background: var(--accent-green); }
        .step-icon.failed { background: var(--accent-red); }
        .step-icon.running { background: var(--accent-yellow); }

        .step-info {
            flex: 1;
        }

        .step-name {
            font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 0.25rem;
        }

        .step-meta {
            display: flex;
            gap: 1rem;
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        /* Artifacts list */
        .artifacts-list {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .artifact-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.5rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-light);
            border-radius: 3px;
            font-size: 0.875rem;
        }

        .artifact-icon {
            color: var(--text-muted);
        }

        .artifact-name {
            flex: 1;
            font-family: var(--font-mono);
            color: var(--text-primary);
        }

        .artifact-size {
            color: var(--text-muted);
            font-size: 0.75rem;
        }

        /* Raw logs viewer */
        .logs-viewer {
            background: #1a1a1a;
            color: #e0e0e0;
            padding: 1rem;
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            line-height: 1.4;
            max-height: 500px;
            overflow-y: auto;
        }

        .log-line {
            display: flex;
            gap: 1rem;
            padding: 0.25rem 0;
        }

        .log-line:hover {
            background: rgba(255,255,255,0.05);
        }

        .log-number {
            color: #666;
            width: 40px;
            text-align: right;
            user-select: none;
        }

        .log-content {
            flex: 1;
            word-break: break-all;
        }

        /* Loading and error states */
        .loading {
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.875rem;
        }

        .error {
            background: #ffebee;
            color: #c62828;
            padding: 1rem;
            border: 1px solid #ffcdd2;
            border-radius: 4px;
            margin: 1rem 0;
        }

        /* Monospace elements */
        .mono {
            font-family: var(--font-mono);
            font-size: 0.875rem;
        }

        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-primary);
        }

        ::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Osiris Session Logs</h1>
            <p class="subtitle">Real-time monitoring and analysis of pipeline executions</p>
        </div>

        <!-- Stats Overview -->
        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="total-sessions">0</div>
                <div class="stat-label">Total Sessions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="success-rate">0%</div>
                <div class="stat-label">Success Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="active-sessions">0</div>
                <div class="stat-label">Active Sessions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="total-rows">0</div>
                <div class="stat-label">Total Rows Processed</div>
            </div>
        </div>

        <!-- Overview View -->
        <div id="overview-view">
            <div class="filters-section">
                <div class="filters-header">Filters</div>

                <!-- Session Type Filters -->
                <div class="type-filters">
                    <div class="type-filter">
                        <input type="checkbox" id="type-chat" checked>
                        <label for="type-chat">
                            <span class="type-badge type-chat">Chat</span>
                            <span class="type-count" id="count-chat">(0)</span>
                        </label>
                    </div>
                    <div class="type-filter">
                        <input type="checkbox" id="type-compile" checked>
                        <label for="type-compile">
                            <span class="type-badge type-compile">Compile</span>
                            <span class="type-count" id="count-compile">(0)</span>
                        </label>
                    </div>
                    <div class="type-filter">
                        <input type="checkbox" id="type-connections" checked>
                        <label for="type-connections">
                            <span class="type-badge type-connections">Connections</span>
                            <span class="type-count" id="count-connections">(0)</span>
                        </label>
                    </div>
                    <div class="type-filter">
                        <input type="checkbox" id="type-ephemeral" checked>
                        <label for="type-ephemeral">
                            <span class="type-badge type-ephemeral">Ephemeral</span>
                            <span class="type-count" id="count-ephemeral">(0)</span>
                        </label>
                    </div>
                    <div class="type-filter">
                        <input type="checkbox" id="type-run" checked>
                        <label for="type-run">
                            <span class="type-badge type-run">Run</span>
                            <span class="type-count" id="count-run">(0)</span>
                        </label>
                    </div>
                    <div class="type-filter">
                        <input type="checkbox" id="type-test" checked>
                        <label for="type-test">
                            <span class="type-badge type-test">Test</span>
                            <span class="type-count" id="count-test">(0)</span>
                        </label>
                    </div>
                    <div class="type-filter">
                        <input type="checkbox" id="type-other" checked>
                        <label for="type-other">
                            <span class="type-badge type-other">Other</span>
                            <span class="type-count" id="count-other">(0)</span>
                        </label>
                    </div>
                </div>

                <div class="filters-grid">
                    <div class="filter-group">
                        <label class="filter-label">Status</label>
                        <select id="status-filter">
                            <option value="">All Status</option>
                            <option value="success">Success</option>
                            <option value="failed">Failed</option>
                            <option value="running">Running</option>
                            <option value="unknown">Unknown</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Label</label>
                        <input type="text" id="label-filter" placeholder="Filter by label">
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Session ID</label>
                        <input type="text" id="search-filter" placeholder="Search session ID">
                    </div>
                </div>

                <div style="display: flex; gap: 0.75rem; margin-top: 0.75rem;">
                    <button class="btn" onclick="applyFilters()">Apply</button>
                    <button class="btn-secondary" onclick="clearFilters()">Clear</button>
                </div>
            </div>

            <!-- Timeline with description -->
            <div class="timeline-section">
                <div class="timeline-header">
                    <div class="timeline-title">Session Timeline</div>
                    <div class="timeline-help">Hover over points to see details • Click to view session</div>
                </div>
                <canvas id="timeline"></canvas>
                <div class="timeline-tooltip" id="timeline-tooltip"></div>
            </div>

            <div class="table-container">
                <div id="sessions-table-container">
                    <div class="loading">Loading sessions...</div>
                </div>
            </div>
        </div>

        <!-- Detail View -->
        <div id="detail-view">
            <div id="detail-content"></div>
        </div>
    </div>

    <script>
        // Embed data directly
        const embeddedData = """
    )

    # Add the minified data
    html_parts.append(minified_data)

    # Add session details
    html_parts.append(
        """;
        const sessionDetails = """
    )

    # Add the minified session details
    html_parts.append(minified_details)

    # Add the rest of the JavaScript
    html_parts.append(
        """;

        let allSessions = [];
        let currentSession = null;
        let sessionTypeCounts = {
            chat: 0,
            compile: 0,
            connections: 0,
            ephemeral: 0,
            run: 0,
            test: 0,
            other: 0
        };

        // Helper function to classify session type
        function getSessionType(sessionId) {
            if (sessionId.includes('chat')) return 'chat';
            if (sessionId.includes('compile')) return 'compile';
            if (sessionId.includes('connection')) return 'connections';
            if (sessionId.includes('ephemeral')) return 'ephemeral';
            if (sessionId.includes('run')) return 'run';
            if (sessionId.includes('test') || sessionId.includes('validation')) return 'test';
            return 'other';
        }

        // Load sessions on page load
        window.addEventListener('load', async () => {
            await loadSessions();

            // Handle hash navigation
            if (window.location.hash) {
                const sessionId = window.location.hash.substring(1).replace('session=', '');
                if (sessionId) {
                    showDetail(sessionId);
                }
            }
        });

        async function loadSessions() {
            try {
                // Use embedded data instead of fetching
                const data = embeddedData;
                allSessions = data.sessions || [];

                // Ensure all sessions have required fields
                allSessions = allSessions.map(session => ({
                    ...session,
                    status: session.status || 'unknown',
                    started_at: session.started_at || new Date().toISOString(),
                    duration_ms: session.duration_ms || 0,
                    session_type: getSessionType(session.session_id)
                }));

                // Count session types
                sessionTypeCounts = {
                    chat: 0,
                    compile: 0,
                    connections: 0,
                    ephemeral: 0,
                    run: 0,
                    test: 0,
                    other: 0
                };

                allSessions.forEach(session => {
                    const type = session.session_type;
                    sessionTypeCounts[type] = (sessionTypeCounts[type] || 0) + 1;
                });

                // Update type counts in UI
                Object.keys(sessionTypeCounts).forEach(type => {
                    const countEl = document.getElementById(`count-${type}`);
                    if (countEl) {
                        countEl.textContent = `(${sessionTypeCounts[type]})`;
                    }
                });

                updateStats();
                renderTable(allSessions);
                drawTimeline(allSessions);
            } catch (error) {
                document.getElementById('sessions-table-container').innerHTML =
                    '<div class="error">Failed to load sessions: ' + error.message + '</div>';
            }
        }

        function updateStats() {
            // Total sessions
            document.getElementById('total-sessions').textContent = allSessions.length;

            // Success rate
            const successCount = allSessions.filter(s => s.status === 'success').length;
            const successRate = allSessions.length > 0 ?
                Math.round((successCount / allSessions.length) * 100) : 0;
            document.getElementById('success-rate').textContent = successRate + '%';

            // Active sessions
            const activeCount = allSessions.filter(s => s.status === 'running').length;
            document.getElementById('active-sessions').textContent = activeCount;

            // Total rows processed
            const totalRows = allSessions.reduce((sum, s) => sum + (s.rows_out || 0), 0);
            document.getElementById('total-rows').textContent = formatNumber(totalRows);
        }

        function renderTable(sessions) {
            if (sessions.length === 0) {
                document.getElementById('sessions-table-container').innerHTML =
                    '<div class="loading">No sessions found</div>';
                return;
            }

            let html = '<table><thead><tr>';
            html += '<th>Type</th><th>Started At</th><th>Session ID</th><th>Pipeline</th>';
            html += '<th>Status</th><th>Duration</th><th>Steps</th><th>Rows In/Out</th><th>Errors</th>';
            html += '</tr></thead><tbody>';

            for (const session of sessions) {
                const type = session.session_type;
                const startTime = session.started_at ?
                    new Date(session.started_at).toLocaleString() : 'N/A';
                const duration = formatDuration(session.duration_ms);

                html += '<tr>';
                html += '<td><span class="type-badge type-' + type + '">' + type + '</span></td>';
                html += '<td>' + startTime + '</td>';
                html += '<td class="clickable mono" onclick="showDetail(\'' + escapeHtml(session.session_id) + '\')">';
                html += escapeHtml(session.session_id) + '</td>';
                html += '<td>' + escapeHtml(session.pipeline_name || 'N/A') + '</td>';
                html += '<td><span class="status status-' + session.status + '">' + session.status + '</span></td>';
                html += '<td>' + duration + '</td>';
                html += '<td>' + (session.steps_ok || 0) + '/' + (session.steps_total || 0) + '</td>';
                html += '<td>' + formatNumber(session.rows_in || 0) + ' / ' + formatNumber(session.rows_out || 0) + '</td>';
                html += '<td>' + (session.errors || 0) + '</td>';
                html += '</tr>';
            }

            html += '</tbody></table>';
            document.getElementById('sessions-table-container').innerHTML = html;
        }

        async function showDetail(sessionId) {
            document.getElementById('overview-view').style.display = 'none';
            document.getElementById('detail-view').classList.add('active');
            window.location.hash = 'session=' + sessionId;

            try {
                // Use embedded session details instead of fetching
                const session = sessionDetails[sessionId] || allSessions.find(s => s.session_id === sessionId);
                if (!session) {
                    throw new Error('Session not found');
                }
                currentSession = session;
                renderDetail(session);
            } catch (error) {
                document.getElementById('detail-content').innerHTML =
                    '<div class="error">Failed to load session details: ' + error.message + '</div>';
            }
        }

        function renderDetail(session) {
            const type = getSessionType(session.session_id);
            const logs = session.logs || {};
            const events = logs.events || [];
            const metrics = logs.metrics || [];
            const artifacts = logs.artifacts || [];

            let html = '<div class="detail-header">';
            html += '<button onclick="showOverview()" class="btn-secondary">← Back</button>';
            html += '<h2><span class="mono">' + escapeHtml(session.session_id) + '</span></h2>';
            html += '<span class="type-badge type-' + type + '">' + type + '</span>';
            html += '<span class="status status-' + (session.status || 'unknown') + '">' + (session.status || 'unknown') + '</span>';
            html += '</div>';

            // Tabs
            html += '<div class="tabs">';
            html += '<button class="tab active" onclick="showTab(\'overview\')">Overview</button>';
            html += '<button class="tab" onclick="showTab(\'events\')">Events (' + events.length + ')</button>';
            html += '<button class="tab" onclick="showTab(\'metrics\')">Metrics (' + metrics.length + ')</button>';
            html += '<button class="tab" onclick="showTab(\'steps\')">Steps</button>';
            html += '<button class="tab" onclick="showTab(\'artifacts\')">Artifacts (' + artifacts.length + ')</button>';
            html += '<button class="tab" onclick="showTab(\'raw\')">Raw Logs</button>';
            html += '</div>';

            // Tab contents
            html += '<div class="tab-content active" id="tab-overview">';
            html += renderOverviewTab(session);
            html += '</div>';

            html += '<div class="tab-content" id="tab-events">';
            html += renderEventsTab(events);
            html += '</div>';

            html += '<div class="tab-content" id="tab-metrics">';
            html += renderMetricsTab(metrics);
            html += '</div>';

            html += '<div class="tab-content" id="tab-steps">';
            html += renderStepsTab(events);
            html += '</div>';

            html += '<div class="tab-content" id="tab-artifacts">';
            html += renderArtifactsTab(artifacts);
            html += '</div>';

            html += '<div class="tab-content" id="tab-raw">';
            html += renderRawTab(events, metrics);
            html += '</div>';

            document.getElementById('detail-content').innerHTML = html;
        }

        function renderOverviewTab(session) {
            let html = '';

            if (session.pipeline_name) {
                html += '<p style="margin-bottom: 1rem;">Pipeline: <strong>' + escapeHtml(session.pipeline_name) + '</strong></p>';
            }

            html += '<div class="metrics-grid">';

            html += '<div class="metric-card">';
            html += '<div class="metric-label">Started At</div>';
            html += '<div class="metric-value" style="font-size: 1rem;">' +
                (session.started_at ? new Date(session.started_at).toLocaleString() : 'N/A') + '</div>';
            html += '</div>';

            html += '<div class="metric-card">';
            html += '<div class="metric-label">Duration</div>';
            html += '<div class="metric-value">' + formatDuration(session.duration_ms || 0) + '</div>';
            html += '</div>';

            if (session.steps) {
                html += '<div class="metric-card">';
                html += '<div class="metric-label">Steps Completed</div>';
                html += '<div class="metric-value">' + (session.steps.completed || 0) + '/' + (session.steps.total || 0) + '</div>';
                html += '</div>';

                html += '<div class="metric-card">';
                html += '<div class="metric-label">Success Rate</div>';
                html += '<div class="metric-value">' + ((session.steps.success_rate || 0) * 100).toFixed(1) + '%</div>';
                html += '</div>';
            }

            if (session.data_flow) {
                html += '<div class="metric-card">';
                html += '<div class="metric-label">Rows In</div>';
                html += '<div class="metric-value">' + formatNumber(session.data_flow.rows_in || 0) + '</div>';
                html += '</div>';

                html += '<div class="metric-card">';
                html += '<div class="metric-label">Rows Out</div>';
                html += '<div class="metric-value">' + formatNumber(session.data_flow.rows_out || 0) + '</div>';
                html += '</div>';
            }

            if (session.diagnostics) {
                html += '<div class="metric-card">';
                html += '<div class="metric-label">Errors</div>';
                html += '<div class="metric-value">' + (session.diagnostics.errors || 0) + '</div>';
                html += '</div>';

                html += '<div class="metric-card">';
                html += '<div class="metric-label">Warnings</div>';
                html += '<div class="metric-value">' + (session.diagnostics.warnings || 0) + '</div>';
                html += '</div>';
            }

            html += '</div>';

            if (session.data_flow && session.data_flow.tables && session.data_flow.tables.length > 0) {
                html += '<div style="margin-top: 1.5rem;">';
                html += '<h3 style="margin-bottom: 0.75rem; font-size: 1rem;">Tables Accessed</h3>';
                html += '<p>';
                session.data_flow.tables.forEach(table => {
                    html += '<span class="type-badge type-other" style="margin-right: 0.5rem;">' + escapeHtml(table) + '</span>';
                });
                html += '</p></div>';
            }

            return html;
        }

        function renderEventsTab(events) {
            if (!events || events.length === 0) {
                return '<div class="loading">No events recorded</div>';
            }

            let html = '<div class="events-timeline">';

            events.forEach((event, index) => {
                const time = event.ts ? new Date(event.ts).toLocaleTimeString() : '';
                const eventType = event.event || 'unknown';

                html += '<div class="event-item">';
                html += '<div class="event-time">' + time + '</div>';
                html += '<div class="event-type">' + escapeHtml(eventType) + '</div>';
                html += '<div class="event-details">';

                // Show relevant details based on event type
                if (event.step_id) html += 'step: ' + event.step_id + ' ';
                if (event.duration) html += 'duration: ' + (event.duration * 1000).toFixed(0) + 'ms ';
                if (event.rows_read) html += 'rows_read: ' + event.rows_read + ' ';
                if (event.rows_written) html += 'rows_written: ' + event.rows_written + ' ';
                if (event.table) html += 'table: ' + event.table + ' ';
                if (event.error) html += 'error: ' + event.error + ' ';

                html += '</div>';
                html += '</div>';
            });

            html += '</div>';
            return html;
        }

        function renderMetricsTab(metrics) {
            if (!metrics || metrics.length === 0) {
                return '<div class="loading">No metrics recorded</div>';
            }

            // Group metrics by type
            const groupedMetrics = {};
            metrics.forEach(metric => {
                const key = metric.metric || 'unknown';
                if (!groupedMetrics[key]) {
                    groupedMetrics[key] = [];
                }
                groupedMetrics[key].push(metric);
            });

            let html = '<div class="metrics-grid">';

            for (const [key, values] of Object.entries(groupedMetrics)) {
                html += '<div class="metric-card">';
                html += '<div class="metric-label">' + escapeHtml(key) + '</div>';

                if (values.length === 1) {
                    const value = values[0].value;
                    const unit = values[0].unit || '';
                    html += '<div class="metric-value">' + formatMetricValue(value) + ' ' + unit + '</div>';
                } else {
                    // Show aggregated values
                    const total = values.reduce((sum, m) => sum + (m.value || 0), 0);
                    html += '<div class="metric-value">' + formatMetricValue(total) + '</div>';
                    html += '<div style="font-size: 0.75rem; color: var(--text-muted);">' + values.length + ' measurements</div>';
                }

                html += '</div>';
            }

            html += '</div>';
            return html;
        }

        function renderStepsTab(events) {
            // Extract step information from events
            const steps = {};

            events.forEach(event => {
                if (event.step_id) {
                    if (!steps[event.step_id]) {
                        steps[event.step_id] = {
                            id: event.step_id,
                            driver: event.driver,
                            start: null,
                            end: null,
                            duration: 0,
                            status: 'unknown',
                            metrics: {}
                        };
                    }

                    const step = steps[event.step_id];

                    if (event.event === 'step_start') {
                        step.start = event.ts;
                        step.driver = event.driver;
                        step.status = 'running';
                    } else if (event.event === 'step_complete') {
                        step.end = event.ts;
                        step.duration = event.duration || 0;
                        step.status = 'success';
                    } else if (event.event === 'step_error') {
                        step.status = 'failed';
                        step.error = event.error;
                    }

                    // Collect metrics
                    if (event.rows_read) step.metrics.rows_read = event.rows_read;
                    if (event.rows_written) step.metrics.rows_written = event.rows_written;
                }
            });

            if (Object.keys(steps).length === 0) {
                return '<div class="loading">No steps recorded</div>';
            }

            let html = '<div class="steps-flow">';

            Object.values(steps).forEach(step => {
                html += '<div class="step-item">';
                html += '<div class="step-icon ' + step.status + '">';
                html += step.status === 'success' ? '✓' : (step.status === 'failed' ? '✗' : '○');
                html += '</div>';

                html += '<div class="step-info">';
                html += '<div class="step-name">' + escapeHtml(step.id) + '</div>';
                html += '<div class="step-meta">';

                if (step.driver) html += '<span>Driver: ' + step.driver + '</span>';
                if (step.duration) html += '<span>Duration: ' + (step.duration * 1000).toFixed(0) + 'ms</span>';
                if (step.metrics.rows_read) html += '<span>Rows read: ' + step.metrics.rows_read + '</span>';
                if (step.metrics.rows_written) html += '<span>Rows written: ' + step.metrics.rows_written + '</span>';

                html += '</div>';
                if (step.error) {
                    html += '<div style="color: var(--accent-red); font-size: 0.75rem; margin-top: 0.25rem;">' +
                        escapeHtml(step.error) + '</div>';
                }
                html += '</div>';

                html += '</div>';
            });

            html += '</div>';
            return html;
        }

        function renderArtifactsTab(artifacts) {
            if (!artifacts || artifacts.length === 0) {
                return '<div class="loading">No artifacts recorded</div>';
            }

            let html = '<div class="artifacts-list">';

            artifacts.forEach(artifact => {
                html += '<div class="artifact-item">';
                html += '<div class="artifact-icon">' + (artifact.type === 'directory' ? '📁' : '📄') + '</div>';
                html += '<div class="artifact-name">' + escapeHtml(artifact.name) + '</div>';
                if (artifact.size !== null) {
                    html += '<div class="artifact-size">' + formatFileSize(artifact.size) + '</div>';
                }
                html += '</div>';
            });

            html += '</div>';
            return html;
        }

        function renderRawTab(events, metrics) {
            let html = '<div class="logs-viewer">';

            let lineNumber = 1;

            // Show events
            if (events && events.length > 0) {
                html += '<div style="color: #4ade80; margin-bottom: 1rem;">// Events</div>';
                events.forEach(event => {
                    html += '<div class="log-line">';
                    html += '<div class="log-number">' + lineNumber++ + '</div>';
                    html += '<div class="log-content">' + escapeHtml(JSON.stringify(event)) + '</div>';
                    html += '</div>';
                });
            }

            // Show metrics
            if (metrics && metrics.length > 0) {
                html += '<div style="color: #4ade80; margin: 1rem 0;">// Metrics</div>';
                metrics.forEach(metric => {
                    html += '<div class="log-line">';
                    html += '<div class="log-number">' + lineNumber++ + '</div>';
                    html += '<div class="log-content">' + escapeHtml(JSON.stringify(metric)) + '</div>';
                    html += '</div>';
                });
            }

            html += '</div>';
            return html;
        }

        function showTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            event.target.classList.add('active');

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById('tab-' + tabName).classList.add('active');
        }

        function showOverview() {
            document.getElementById('detail-view').classList.remove('active');
            document.getElementById('overview-view').style.display = 'block';
            window.location.hash = '';
        }

        function applyFilters() {
            const statusFilter = document.getElementById('status-filter').value;
            const labelFilter = document.getElementById('label-filter').value.toLowerCase();
            const searchFilter = document.getElementById('search-filter').value.toLowerCase();

            // Get checked session types
            const checkedTypes = [];
            ['chat', 'compile', 'connections', 'ephemeral', 'run', 'test', 'other'].forEach(type => {
                if (document.getElementById(`type-${type}`).checked) {
                    checkedTypes.push(type);
                }
            });

            const filtered = allSessions.filter(session => {
                // Type filter
                if (!checkedTypes.includes(session.session_type)) return false;

                // Status filter
                if (statusFilter && session.status !== statusFilter) return false;

                // Label filter
                if (labelFilter && !session.labels?.some(l => l.toLowerCase().includes(labelFilter))) return false;

                // Search filter
                if (searchFilter && !session.session_id.toLowerCase().includes(searchFilter)) return false;

                return true;
            });

            renderTable(filtered);
        }

        function clearFilters() {
            document.getElementById('status-filter').value = '';
            document.getElementById('label-filter').value = '';
            document.getElementById('search-filter').value = '';

            // Check all type filters
            ['chat', 'compile', 'connections', 'ephemeral', 'run', 'test', 'other'].forEach(type => {
                document.getElementById(`type-${type}`).checked = true;
            });

            renderTable(allSessions);
        }

        function drawTimeline(sessions) {
            const canvas = document.getElementById('timeline');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = 100;

            if (sessions.length === 0) return;

            // Clear canvas
            ctx.fillStyle = '#fafafa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Find time range
            let minTime = Infinity, maxTime = -Infinity;
            sessions.forEach(s => {
                if (s.started_at) {
                    const t = new Date(s.started_at).getTime();
                    minTime = Math.min(minTime, t);
                    maxTime = Math.max(maxTime, t);
                }
            });

            if (minTime === Infinity) return;

            const timeRange = maxTime - minTime || 1;
            const padding = 20;
            const width = canvas.width - 2 * padding;
            const height = canvas.height - 2 * padding;

            // Draw grid lines
            ctx.strokeStyle = '#e5e5e5';
            ctx.lineWidth = 1;
            for (let i = 0; i <= 4; i++) {
                const y = padding + (i * height / 4);
                ctx.beginPath();
                ctx.moveTo(padding, y);
                ctx.lineTo(canvas.width - padding, y);
                ctx.stroke();
            }

            // Store session positions for hover
            const sessionPositions = [];

            // Draw sessions
            sessions.forEach((session, index) => {
                if (!session.started_at) return;

                const startTime = new Date(session.started_at).getTime();
                const x = padding + ((startTime - minTime) / timeRange) * width;
                const y = padding + (index % 4) * 20 + 10;

                // Store position for hover detection
                sessionPositions.push({
                    x, y,
                    session,
                    radius: 4
                });

                // Color by status
                if (session.status === 'success') ctx.fillStyle = '#00cc88';
                else if (session.status === 'failed') ctx.fillStyle = '#ff3333';
                else if (session.status === 'running') ctx.fillStyle = '#ffcc00';
                else ctx.fillStyle = '#999999';

                // Draw session marker
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, 2 * Math.PI);
                ctx.fill();

                // Draw connection line
                if (index > 0) {
                    const prevSession = sessions[index - 1];
                    if (prevSession.started_at) {
                        const prevTime = new Date(prevSession.started_at).getTime();
                        const prevX = padding + ((prevTime - minTime) / timeRange) * width;
                        const prevY = padding + ((index - 1) % 4) * 20 + 10;

                        ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
                        ctx.lineWidth = 1;
                        ctx.beginPath();
                        ctx.moveTo(prevX, prevY);
                        ctx.lineTo(x, y);
                        ctx.stroke();
                    }
                }
            });

            // Add hover handler
            const tooltip = document.getElementById('timeline-tooltip');
            canvas.addEventListener('mousemove', (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                let hovered = null;
                for (const pos of sessionPositions) {
                    const dist = Math.sqrt(Math.pow(x - pos.x, 2) + Math.pow(y - pos.y, 2));
                    if (dist <= pos.radius + 2) {
                        hovered = pos.session;
                        break;
                    }
                }

                if (hovered) {
                    tooltip.style.display = 'block';
                    tooltip.style.left = e.clientX + 10 + 'px';
                    tooltip.style.top = e.clientY - 30 + 'px';
                    tooltip.innerHTML =
                        '<strong>' + hovered.session_id + '</strong><br>' +
                        'Status: ' + hovered.status + '<br>' +
                        'Duration: ' + formatDuration(hovered.duration_ms);
                    canvas.style.cursor = 'pointer';
                } else {
                    tooltip.style.display = 'none';
                    canvas.style.cursor = 'crosshair';
                }
            });

            canvas.addEventListener('mouseleave', () => {
                tooltip.style.display = 'none';
            });

            canvas.addEventListener('click', (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                for (const pos of sessionPositions) {
                    const dist = Math.sqrt(Math.pow(x - pos.x, 2) + Math.pow(y - pos.y, 2));
                    if (dist <= pos.radius + 2) {
                        showDetail(pos.session.session_id);
                        break;
                    }
                }
            });
        }

        function formatDuration(ms) {
            if (!ms || ms === 0) return '0s';
            const seconds = Math.floor(ms / 1000);
            const minutes = Math.floor(seconds / 60);
            const hours = Math.floor(minutes / 60);

            if (hours > 0) return hours + 'h ' + (minutes % 60) + 'm';
            if (minutes > 0) return minutes + 'm ' + (seconds % 60) + 's';
            if (ms < 1000) return ms + 'ms';
            return seconds + 's';
        }

        function formatNumber(num) {
            return num.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");
        }

        function formatMetricValue(value) {
            if (typeof value === 'number') {
                if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
                if (value >= 1000) return (value / 1000).toFixed(1) + 'K';
                if (value < 1) return value.toFixed(3);
                return value.toFixed(0);
            }
            return value;
        }

        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Add event listeners for type filters
        document.addEventListener('DOMContentLoaded', () => {
            ['chat', 'compile', 'connections', 'ephemeral', 'run', 'test', 'other'].forEach(type => {
                const checkbox = document.getElementById(`type-${type}`);
                if (checkbox) {
                    checkbox.addEventListener('change', applyFilters);
                }
            });
        });
    </script>
</body>
</html>"""
    )

    # Join all parts
    html = "".join(html_parts)

    return html


def generate_single_session_html(session_id: str, logs_dir: str = "./logs", output_dir: str = "dist/logs") -> str:
    """Generate HTML report for a single session."""
    reader = SessionReader(logs_dir)

    # Handle special cases
    if session_id == "last":
        session = reader.get_last_session()
        if not session:
            raise ValueError("No sessions found")
        session_id = session.session_id
    else:
        session = reader.read_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

    # Create output directory for this session
    session_output_dir = Path(output_dir) / session_id
    session_output_dir.mkdir(parents=True, exist_ok=True)

    # Generate session JSON
    session_json = to_session_json(session, logs_dir)
    session_data = json.loads(session_json)

    # Add full logs to session data
    session_logs = read_session_logs(logs_dir, session_id)
    session_data["logs"] = session_logs

    # Generate single-session HTML with just this session
    data = {
        "sessions": [session.__dict__],
        "generated_at": session.started_at or datetime.now().isoformat(),
    }
    session_details = {session_id: session_data}

    html_content = generate_index_html(json.dumps(data), session_details)
    html_path = session_output_dir / "index.html"
    html_path.write_text(html_content)

    return str(html_path.absolute())


if __name__ == "__main__":
    # Example usage
    generate_html_report(limit=50)
    print("Enhanced HTML report generated in dist/logs/")
