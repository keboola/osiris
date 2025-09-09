#!/usr/bin/env python3
"""Fixed HTML generator that properly embeds JSON data."""

import json
from pathlib import Path
from typing import Optional

from osiris.core.logs_serialize import to_index_json, to_session_json
from osiris.core.session_reader import SessionReader


def generate_html_report(
    logs_dir: str = "./logs",
    output_dir: str = "dist/logs",
    status_filter: Optional[str] = None,
    label_filter: Optional[str] = None,
    since_filter: Optional[str] = None,
    limit: Optional[int] = None,
) -> None:
    """Generate static HTML report from session logs."""
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
    """Generate the single-page HTML application with embedded data."""

    # Parse and minify JSON
    data_obj = json.loads(data_json)
    minified_data = json.dumps(data_obj, separators=(",", ":"))
    minified_details = json.dumps(session_details, separators=(",", ":"))

    # Build HTML in parts to avoid escaping issues
    html_parts = []

    # Start of HTML
    html_parts.append(
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Osiris Logs Browser</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1 { margin-bottom: 20px; color: #2c3e50; }
        .filters { background: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap; }
        .filters input, .filters select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }
        .btn { padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .btn:hover { background: #2980b9; }
        .btn-secondary { background: #95a5a6; }
        .btn-secondary:hover { background: #7f8c8d; }
        table { width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th { background: #34495e; color: white; padding: 12px; text-align: left; }
        td { padding: 12px; border-bottom: 1px solid #ecf0f1; }
        tr:hover { background: #f8f9fa; }
        .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .status-success { background: #d4edda; color: #155724; }
        .status-failed { background: #f8d7da; color: #721c24; }
        .status-running { background: #fff3cd; color: #856404; }
        .status-unknown { background: #e2e3e5; color: #383d41; }
        .clickable { color: #3498db; cursor: pointer; text-decoration: underline; }
        .clickable:hover { color: #2980b9; }
        .label { background: #e7f3ff; color: #004085; padding: 2px 6px; border-radius: 3px; margin-right: 4px; font-size: 12px; }
        #detail-view { display: none; }
        #detail-view.active { display: block; }
        .session-detail-header { margin-bottom: 20px; }
        .session-detail-header h2 { display: inline-block; margin-right: 20px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .metric-card { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric-label { font-size: 12px; color: #7f8c8d; margin-bottom: 5px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .loading { text-align: center; padding: 40px; color: #7f8c8d; }
        .error { background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0; }
        #timeline { width: 100%; height: 150px; margin: 20px 0; border: 1px solid #ddd; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Osiris Logs Browser</h1>

        <!-- Overview View -->
        <div id="overview-view">
            <div class="filters">
                <select id="status-filter">
                    <option value="">All Status</option>
                    <option value="success">Success</option>
                    <option value="failed">Failed</option>
                    <option value="running">Running</option>
                    <option value="unknown">Unknown</option>
                </select>
                <input type="text" id="label-filter" placeholder="Filter by label">
                <input type="text" id="search-filter" placeholder="Search session ID">
                <button class="btn" onclick="applyFilters()">Apply Filters</button>
                <button class="btn btn-secondary" onclick="clearFilters()">Clear</button>
            </div>

            <canvas id="timeline"></canvas>

            <div id="sessions-table-container">
                <div class="loading">Loading sessions...</div>
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
                renderTable(allSessions);
                drawTimeline(allSessions);
            } catch (error) {
                document.getElementById('sessions-table-container').innerHTML =
                    '<div class="error">Failed to load sessions: ' + error.message + '</div>';
            }
        }

        function renderTable(sessions) {
            if (sessions.length === 0) {
                document.getElementById('sessions-table-container').innerHTML =
                    '<div class="loading">No sessions found</div>';
                return;
            }

            let html = '<table><thead><tr>';
            html += '<th>Started At</th><th>Session ID</th><th>Pipeline</th><th>Labels</th>';
            html += '<th>Status</th><th>Duration</th><th>Steps</th><th>Rows In/Out</th><th>Errors</th>';
            html += '</tr></thead><tbody>';

            for (const session of sessions) {
                const startTime = session.started_at ?
                    new Date(session.started_at).toLocaleString() : 'N/A';
                const duration = formatDuration(session.duration_ms);
                const labels = (session.labels || []).map(l =>
                    '<span class="label">' + escapeHtml(l) + '</span>').join('');

                html += '<tr>';
                html += '<td>' + startTime + '</td>';
                html += '<td class="clickable" onclick="showDetail(\\\'' + escapeHtml(session.session_id) + '\\\')">';
                html += escapeHtml(session.session_id) + '</td>';
                html += '<td>' + escapeHtml(session.pipeline_name || 'unknown') + '</td>';
                html += '<td>' + labels + '</td>';
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
                const session = sessionDetails[sessionId];
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
            let html = '<div class="session-detail-header">';
            html += '<button onclick="showOverview()" class="btn btn-secondary">← Back to List</button>';
            html += '<h2>Session: ' + escapeHtml(session.session_id) + '</h2>';
            html += '<p>Pipeline: <strong>' + escapeHtml(session.pipeline_name || 'unknown') + '</strong></p>';
            html += '</div>';

            html += '<div class="metrics-grid">';
            html += '<div class="metric-card"><div class="metric-label">Status</div>';
            html += '<div class="metric-value"><span class="status status-' + session.status + '">' + session.status + '</span></div></div>';

            html += '<div class="metric-card"><div class="metric-label">Duration</div>';
            html += '<div class="metric-value">' + formatDuration(session.duration_ms) + '</div></div>';

            if (session.steps) {
                html += '<div class="metric-card"><div class="metric-label">Steps Completed</div>';
                html += '<div class="metric-value">' + (session.steps.completed || 0) + '/' + (session.steps.total || 0) + '</div></div>';

                html += '<div class="metric-card"><div class="metric-label">Success Rate</div>';
                html += '<div class="metric-value">' + ((session.steps.success_rate || 0) * 100).toFixed(1) + '%</div></div>';
            }

            if (session.data_flow) {
                html += '<div class="metric-card"><div class="metric-label">Rows In</div>';
                html += '<div class="metric-value">' + formatNumber(session.data_flow.rows_in || 0) + '</div></div>';

                html += '<div class="metric-card"><div class="metric-label">Rows Out</div>';
                html += '<div class="metric-value">' + formatNumber(session.data_flow.rows_out || 0) + '</div></div>';
            }

            if (session.diagnostics) {
                html += '<div class="metric-card"><div class="metric-label">Errors</div>';
                html += '<div class="metric-value">' + (session.diagnostics.errors || 0) + '</div></div>';

                html += '<div class="metric-card"><div class="metric-label">Warnings</div>';
                html += '<div class="metric-value">' + (session.diagnostics.warnings || 0) + '</div></div>';
            }

            html += '</div>';

            if (session.data_flow && session.data_flow.tables && session.data_flow.tables.length > 0) {
                html += '<div class="tables-section"><h3>Tables</h3><p>';
                html += session.data_flow.tables.map(t => '<span class="label">' + escapeHtml(t) + '</span>').join(' ');
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

            const filtered = allSessions.filter(session => {
                if (statusFilter && session.status !== statusFilter) return false;
                if (labelFilter && !session.labels?.some(l => l.toLowerCase().includes(labelFilter))) return false;
                if (searchFilter && !session.session_id.toLowerCase().includes(searchFilter)) return false;
                return true;
            });

            renderTable(filtered);
        }

        function clearFilters() {
            document.getElementById('status-filter').value = '';
            document.getElementById('label-filter').value = '';
            document.getElementById('search-filter').value = '';
            renderTable(allSessions);
        }

        function drawTimeline(sessions) {
            const canvas = document.getElementById('timeline');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = 150;

            if (sessions.length === 0) return;

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

            // Draw sessions
            sessions.forEach((session, index) => {
                if (!session.started_at) return;

                const startTime = new Date(session.started_at).getTime();
                const x = padding + ((startTime - minTime) / timeRange) * width;
                const y = padding + (index % 5) * 25;

                // Color by status
                if (session.status === 'success') ctx.fillStyle = '#28a745';
                else if (session.status === 'failed') ctx.fillStyle = '#dc3545';
                else if (session.status === 'running') ctx.fillStyle = '#ffc107';
                else ctx.fillStyle = '#6c757d';

                ctx.beginPath();
                ctx.arc(x, y, 4, 0, 2 * Math.PI);
                ctx.fill();
            });
        }

        function formatDuration(ms) {
            if (!ms) return 'N/A';
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
    </script>
</body>
</html>"""
    )

    # Join all parts
    html = "".join(html_parts)

    return html


def generate_single_session_html(
    session_id: str, logs_dir: str = "./logs", output_dir: str = "dist/logs"
) -> str:
    """Generate HTML report for a single session.

    Args:
        session_id: Session ID to generate report for
        logs_dir: Directory containing session logs
        output_dir: Output directory for HTML

    Returns:
        Path to generated HTML file
    """
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
        "generated_at": session.started_at or "2025-01-09T00:00:00Z",
    }
    session_details = {session_id: json.loads(session_json)}

    html_content = generate_index_html(json.dumps(data), session_details)
    html_path = session_output_dir / "index.html"
    html_path.write_text(html_content)

    return str(html_path.absolute())


if __name__ == "__main__":
    # Example usage
    generate_html_report(limit=10)
    print("HTML report generated in dist/logs/")
