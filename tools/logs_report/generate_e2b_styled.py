#!/usr/bin/env python3
"""Enhanced HTML generator with e2b.dev-inspired design and session type classification."""

import json
from datetime import datetime
from pathlib import Path

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


def generate_html_report(
    logs_dir: str = "./logs",
    output_dir: str = "dist/logs",
    status_filter: str | None = None,
    label_filter: str | None = None,
    since_filter: str | None = None,
    limit: int | None = None,
) -> None:
    """Generate static HTML report from session logs with e2b.dev-inspired design."""
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

    # Generate JSON files
    index_json = to_index_json(filtered_sessions)
    (output_path / "data.json").write_text(index_json)

    # Individual session JSONs and collect details
    session_details = {}
    for session in filtered_sessions:
        session_json = to_session_json(session, logs_dir)
        (output_path / f"session_{session.session_id}.json").write_text(session_json)
        # Also store for embedding
        session_details[session.session_id] = json.loads(session_json)

    # Generate HTML with embedded data
    html_content = generate_index_html(index_json, session_details)
    (output_path / "index.html").write_text(html_content)


def generate_index_html(data_json: str, session_details: dict) -> str:
    """Generate the single-page HTML application with e2b.dev-inspired design."""

    # Parse and minify JSON
    data_obj = json.loads(data_json)
    minified_data = json.dumps(data_obj, separators=(",", ":"))
    minified_details = json.dumps(session_details, separators=(",", ":"))

    # Build HTML in parts to avoid escaping issues
    html_parts = []

    # Start of HTML with e2b.dev-inspired design
    html_parts.append(
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Osiris Session Logs Browser</title>
    <style>
        /* Base styles inspired by e2b.dev */
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #fafafa;
            --bg-secondary: #ffffff;
            --text-primary: #000000;
            --text-secondary: #666666;
            --text-muted: #999999;
            --border-color: #e5e5e5;
            --accent-blue: #0066ff;
            --accent-green: #00cc88;
            --accent-yellow: #ffcc00;
            --accent-red: #ff3333;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
            --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
            --font-mono: 'SF Mono', Monaco, 'Cascadia Code', monospace;
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
            margin-bottom: 3rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 2rem;
        }

        h1 {
            font-size: 2.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1.125rem;
        }

        /* Stats cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--bg-secondary);
            padding: 1.5rem;
            border: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }

        .stat-card:hover {
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }

        .stat-label {
            font-size: 0.875rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }

        /* Filters section */
        .filters-section {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            padding: 1.5rem;
            margin-bottom: 2rem;
        }

        .filters-header {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            margin-bottom: 1rem;
        }

        .filters-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .filter-group {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .filter-label {
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-secondary);
        }

        input[type="text"], select {
            padding: 0.5rem 0.75rem;
            border: 1px solid var(--border-color);
            background: var(--bg-primary);
            font-size: 0.875rem;
            transition: all 0.2s ease;
        }

        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: var(--accent-blue);
            background: var(--bg-secondary);
        }

        /* Session type filters */
        .type-filters {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            padding: 1rem 0;
            border-top: 1px solid var(--border-color);
            border-bottom: 1px solid var(--border-color);
            margin: 1rem 0;
        }

        .type-filter {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            cursor: pointer;
            user-select: none;
        }

        .type-filter input[type="checkbox"] {
            width: 1.125rem;
            height: 1.125rem;
            cursor: pointer;
        }

        .type-filter label {
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }

        .type-badge {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 0.25rem;
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
            padding: 0.5rem 1rem;
            border: 1px solid var(--text-primary);
            background: var(--text-primary);
            color: var(--bg-secondary);
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
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

        /* Table styles */
        .table-container {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            overflow: hidden;
            margin-bottom: 2rem;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            background: var(--bg-primary);
            padding: 1rem;
            text-align: left;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }

        td {
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
            font-size: 0.875rem;
        }

        tr:hover {
            background: var(--bg-primary);
        }

        /* Status badges */
        .status {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
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

        /* Timeline */
        #timeline {
            width: 100%;
            height: 120px;
            margin: 2rem 0;
            border: 1px solid var(--border-color);
            background: var(--bg-secondary);
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
            gap: 2rem;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        .detail-header h2 {
            font-size: 1.5rem;
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 2rem 0;
        }

        .metric-card {
            background: var(--bg-secondary);
            padding: 1.5rem;
            border: 1px solid var(--border-color);
        }

        .metric-label {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }

        .metric-value {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: var(--text-primary);
        }

        /* Loading and error states */
        .loading {
            text-align: center;
            padding: 3rem;
            color: var(--text-muted);
            font-size: 0.875rem;
        }

        .error {
            background: #ffebee;
            color: #c62828;
            padding: 1rem;
            border: 1px solid #ffcdd2;
            margin: 1rem 0;
        }

        /* Monospace elements */
        .mono {
            font-family: var(--font-mono);
            font-size: 0.875rem;
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
                <div class="filters-header">[ FILTERS ]</div>

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

                <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                    <button class="btn" onclick="applyFilters()">Apply Filters</button>
                    <button class="btn-secondary" onclick="clearFilters()">Clear All</button>
                </div>
            </div>

            <canvas id="timeline"></canvas>

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
        // Embedded data
        const embeddedData = """
    )

    # Add the minified JSON data
    html_parts.append(minified_data)

    # Continue with sessionDetails
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

        // Handle browser back/forward
        window.addEventListener('hashchange', () => {
            if (window.location.hash) {
                const sessionId = window.location.hash.substring(1).replace('session=', '');
                if (sessionId) {
                    showDetail(sessionId);
                } else {
                    showOverview();
                }
            } else {
                showOverview();
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
                html += '<td class="clickable mono" onclick="showDetail(\\\'' + escapeHtml(session.session_id) + '\\\')">';
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

            let html = '<div class="detail-header">';
            html += '<button onclick="showOverview()" class="btn-secondary">← Back</button>';
            html += '<h2>Session: <span class="mono">' + escapeHtml(session.session_id) + '</span></h2>';
            html += '<span class="type-badge type-' + type + '">' + type + '</span>';
            html += '</div>';

            if (session.pipeline_name) {
                html += '<p style="margin-bottom: 1rem;">Pipeline: <strong>' + escapeHtml(session.pipeline_name) + '</strong></p>';
            }

            html += '<div class="metrics-grid">';

            html += '<div class="metric-card">';
            html += '<div class="metric-label">Status</div>';
            html += '<div class="metric-value"><span class="status status-' + (session.status || 'unknown') + '">' + (session.status || 'unknown') + '</span></div>';
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
                html += '<div style="margin-top: 2rem;">';
                html += '<h3 style="margin-bottom: 1rem;">Tables Accessed</h3>';
                html += '<p>';
                session.data_flow.tables.forEach(table => {
                    html += '<span class="type-badge type-other" style="margin-right: 0.5rem;">' + escapeHtml(table) + '</span>';
                });
                html += '</p></div>';
            }

            document.getElementById('detail-content').innerHTML = html;
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
            canvas.height = 120;

            if (sessions.length === 0) return;

            // Clear canvas
            ctx.fillStyle = '#ffffff';
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

            // Draw sessions
            sessions.forEach((session, index) => {
                if (!session.started_at) return;

                const startTime = new Date(session.started_at).getTime();
                const x = padding + ((startTime - minTime) / timeRange) * width;
                const y = padding + (index % 4) * 25 + 10;

                // Color by status
                if (session.status === 'success') ctx.fillStyle = '#00cc88';
                else if (session.status === 'failed') ctx.fillStyle = '#ff3333';
                else if (session.status === 'running') ctx.fillStyle = '#ffcc00';
                else ctx.fillStyle = '#999999';

                // Draw session marker
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, 2 * Math.PI);
                ctx.fill();

                // Draw connection line
                if (index > 0) {
                    const prevSession = sessions[index - 1];
                    if (prevSession.started_at) {
                        const prevTime = new Date(prevSession.started_at).getTime();
                        const prevX = padding + ((prevTime - minTime) / timeRange) * width;
                        const prevY = padding + ((index - 1) % 4) * 25 + 10;

                        ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
                        ctx.lineWidth = 1;
                        ctx.beginPath();
                        ctx.moveTo(prevX, prevY);
                        ctx.lineTo(x, y);
                        ctx.stroke();
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
            return seconds + 's';
        }

        function formatNumber(num) {
            return num.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");
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
            raise ValueError(f"Session not found: {session_id}")

    # Create output directory for this session
    session_output_dir = Path(output_dir) / session_id
    session_output_dir.mkdir(parents=True, exist_ok=True)

    # Generate session JSON
    session_json = to_session_json(session, logs_dir)

    # Generate single-session HTML with just this session
    data = {
        "sessions": [session.__dict__],
        "generated_at": session.started_at or datetime.now().isoformat(),
    }
    session_details = {session_id: json.loads(session_json)}

    html_content = generate_index_html(json.dumps(data), session_details)
    html_path = session_output_dir / "index.html"
    html_path.write_text(html_content)

    return str(html_path.absolute())


if __name__ == "__main__":
    # Example usage
    generate_html_report(limit=50)
    print("Enhanced HTML report generated in dist/logs/")
