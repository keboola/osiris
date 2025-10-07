#!/usr/bin/env python3
"""Generate multi-page HTML report from Osiris session logs."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def read_session_logs(logs_dir: str, session_id: str) -> dict[str, Any]:
    """Read full session logs including events and metrics."""
    session_path = Path(logs_dir) / session_id
    result = {"events": [], "metrics": [], "artifacts": []}

    # Read events.jsonl
    events_file = session_path / "events.jsonl"
    if events_file.exists():
        with open(events_file) as f:
            for line in f:
                if line.strip():
                    result["events"].append(json.loads(line))

    # Read metrics.jsonl
    metrics_file = session_path / "metrics.jsonl"
    if metrics_file.exists():
        with open(metrics_file) as f:
            for line in f:
                if line.strip():
                    result["metrics"].append(json.loads(line))

    # List artifacts
    artifacts_dir = session_path / "artifacts"
    if artifacts_dir.exists():
        for item in sorted(artifacts_dir.iterdir()):
            result["artifacts"].append(
                {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )

    return result


def classify_session(session_id: str) -> str:
    """Classify session type based on ID."""
    if session_id.startswith("chat_"):
        return "chat"
    elif session_id.startswith("compile_"):
        return "compile"
    elif session_id.startswith("connections_"):
        return "connections"
    elif session_id.startswith("ephemeral_"):
        return "ephemeral"
    elif session_id.startswith("run_"):
        return "run"
    elif session_id.startswith("test_"):
        return "test"
    else:
        return "other"


def format_duration(ms: float) -> str:
    """Format duration in milliseconds to human readable."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        minutes = ms / 60000
        return f"{minutes:.1f}m"


def format_timestamp(ts_str: str) -> str:
    """Format timestamp to readable format."""
    try:
        # Parse ISO format timestamp
        dt = datetime.fromisoformat(ts_str.replace("+00:00", ""))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return ts_str


def generate_session_page(session: dict[str, Any], logs: dict[str, Any], output_dir: Path) -> None:
    """Generate individual session detail page."""
    session_id = session["session_id"]
    session_type = classify_session(session_id)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Session: {session_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #fafafa;
            color: #1a1a1a;
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #e5e5e5;
        }}
        h1 {{
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
        }}
        .back-link {{
            color: #0066ff;
            text-decoration: none;
            margin-bottom: 1rem;
            display: inline-block;
        }}
        .back-link:hover {{
            text-decoration: underline;
        }}
        .session-type {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
            font-weight: 500;
            background: #e5e5e5;
            color: #333;
            margin-left: 1rem;
        }}
        .session-type.chat {{ background: #e3f2fd; color: #1565c0; }}
        .session-type.compile {{ background: #f3e5f5; color: #7b1fa2; }}
        .session-type.connections {{ background: #e8f5e9; color: #2e7d32; }}
        .session-type.run {{ background: #fff3e0; color: #ef6c00; }}
        .status-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
            font-weight: 500;
            margin-left: 0.5rem;
        }}
        .status-badge.success {{ background: #00cc88; color: white; }}
        .status-badge.failed {{ background: #ff3333; color: white; }}
        .overview {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .overview-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-top: 1rem;
        }}
        .metric {{
            padding: 1rem;
            background: #f5f5f5;
            border-radius: 4px;
        }}
        .metric-label {{
            font-size: 0.875rem;
            color: #666;
            margin-bottom: 0.25rem;
        }}
        .metric-value {{
            font-size: 1.5rem;
            font-weight: 600;
        }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        h2 {{
            font-size: 1.3rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #e5e5e5;
        }}
        .events-list, .metrics-list, .artifacts-list {{
            max-height: 400px;
            overflow-y: auto;
            background: #f9f9f9;
            border-radius: 4px;
            padding: 1rem;
        }}
        .event-item, .metric-item, .artifact-item {{
            padding: 0.75rem;
            margin-bottom: 0.5rem;
            background: white;
            border-radius: 4px;
            border: 1px solid #e5e5e5;
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 0.875rem;
        }}
        .timestamp {{
            color: #666;
            font-size: 0.875rem;
        }}
        .event-name {{
            font-weight: 600;
            color: #0066ff;
        }}
        .empty-state {{
            text-align: center;
            padding: 2rem;
            color: #999;
        }}
        pre {{
            background: #f5f5f5;
            padding: 1rem;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="index.html" class="back-link">← Back to Sessions</a>

        <div class="header">
            <h1>
                {session_id}
                <span class="session-type {session_type}">{session_type.upper()}</span>
                <span class="status-badge {session.get('status', 'unknown')}">{session.get('status', 'unknown').upper()}</span>
            </h1>
            <p style="color: #666; margin-top: 0.5rem;">
                {format_timestamp(session.get('started_at', ''))} →
                {format_timestamp(session.get('finished_at', ''))}
                ({format_duration(session.get('duration_ms', 0))})
            </p>
        </div>

        <div class="overview">
            <h2>Overview</h2>
            <div class="overview-grid">
                <div class="metric">
                    <div class="metric-label">Duration</div>
                    <div class="metric-value">{format_duration(session.get('duration_ms', 0))}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Steps</div>
                    <div class="metric-value">{session.get('steps_ok', 0)}/{session.get('steps_total', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Rows In</div>
                    <div class="metric-value">{session.get('rows_in', 0):,}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Rows Out</div>
                    <div class="metric-value">{session.get('rows_out', 0):,}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Errors</div>
                    <div class="metric-value">{session.get('errors', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Warnings</div>
                    <div class="metric-value">{session.get('warnings', 0)}</div>
                </div>
            </div>
            {f'<p style="margin-top: 1rem;"><strong>Pipeline:</strong> {session.get("pipeline_name")}</p>' if session.get("pipeline_name") else ''}
        </div>

        <div class="section">
            <h2>Events ({len(logs.get('events', []))})</h2>
            <div class="events-list">
                {''.join([f'''
                <div class="event-item">
                    <span class="timestamp">{event.get('ts', '')}</span>
                    <span class="event-name">{event.get('event', '')}</span>
                    {f'<br><small>{json.dumps({k: v for k, v in event.items() if k not in ["ts", "event", "session"]}, indent=2)}</small>' if len([k for k in event if k not in ["ts", "event", "session"]]) > 0 else ''}
                </div>
                ''' for event in logs.get('events', [])][:50]) if logs.get('events') else '<div class="empty-state">No events recorded</div>'}
            </div>
        </div>

        <div class="section">
            <h2>Metrics ({len(logs.get('metrics', []))})</h2>
            <div class="metrics-list">
                {''.join([f'''
                <div class="metric-item">
                    <span class="timestamp">{metric.get('ts', '')}</span>
                    <strong>{metric.get('metric', '')}</strong>: {metric.get('value', '')}
                    {f' {metric.get("unit", "")}' if metric.get("unit") else ''}
                </div>
                ''' for metric in logs.get('metrics', [])][:50]) if logs.get('metrics') else '<div class="empty-state">No metrics recorded</div>'}
            </div>
        </div>

        <div class="section">
            <h2>Artifacts ({len(logs.get('artifacts', []))})</h2>
            <div class="artifacts-list">
                {''.join([f'''
                <div class="artifact-item">
                    📁 {artifact.get('name', '')} ({artifact.get('type', '')})
                </div>
                ''' for artifact in logs.get('artifacts', [])]) if logs.get('artifacts') else '<div class="empty-state">No artifacts generated</div>'}
            </div>
        </div>
    </div>
</body>
</html>"""

    # Write session page
    session_file = output_dir / f"session_{session_id}.html"
    session_file.write_text(html)


def generate_sessions_html(session_types: dict[str, list[dict[str, Any]]]) -> str:
    """Generate HTML for session tables grouped by type."""
    sections = []
    for session_type, type_sessions in sorted(session_types.items()):
        if not type_sessions:
            continue

        # Build rows for this session type
        rows = []
        for s in sorted(type_sessions, key=lambda x: x.get("started_at", ""), reverse=True):
            row = f"""
                        <tr>
                            <td><a href="session_{s['session_id']}.html" class="session-link">{s['session_id']}</a></td>
                            <td><span class="status-badge {s.get('status', 'unknown')}">{s.get('status', 'UNKNOWN').upper()}</span></td>
                            <td>{format_timestamp(s.get('started_at', ''))}</td>
                            <td>{format_duration(s.get('duration_ms', 0))}</td>
                            <td>{s.get('steps_ok', 0)}/{s.get('steps_total', 0)}</td>
                            <td>{s.get('rows_out', 0):,}</td>
                            <td>{s.get('pipeline_name', '-')}</td>
                        </tr>"""
            rows.append(row)

        section = f"""
            <div class="session-type-header">{session_type.upper()} Sessions ({len(type_sessions)})</div>
            <div class="sessions-table">
                <table>
                    <thead>
                        <tr>
                            <th>Session ID</th>
                            <th>Status</th>
                            <th>Started</th>
                            <th>Duration</th>
                            <th>Steps</th>
                            <th>Rows</th>
                            <th>Pipeline</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>"""
        sections.append(section)

    return "".join(sections)


def generate_index_page(sessions: list[dict[str, Any]], output_dir: Path) -> None:
    """Generate the main index page with session list."""

    # Calculate statistics
    total_sessions = len(sessions)
    successful = sum(1 for s in sessions if s.get("status") == "success")
    success_rate = (successful / total_sessions * 100) if total_sessions > 0 else 0
    total_rows = sum(s.get("rows_out", 0) for s in sessions)

    # Group sessions by type
    session_types = {}
    for session in sessions:
        session_type = classify_session(session["session_id"])
        if session_type not in session_types:
            session_types[session_type] = []
        session_types[session_type].append(session)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Osiris Session Logs</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #fafafa;
            color: #1a1a1a;
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #e5e5e5;
        }}
        h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        .subtitle {{
            color: #666;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 2rem 0;
        }}
        .stat-card {{
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.875rem;
        }}
        .sessions-section {{
            margin-top: 2rem;
        }}
        .session-type-header {{
            font-size: 1.2rem;
            font-weight: 600;
            margin: 1.5rem 0 1rem;
            padding: 0.5rem;
            background: #f5f5f5;
            border-radius: 4px;
        }}
        .sessions-table {{
            width: 100%;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            background: #f5f5f5;
            padding: 0.75rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.875rem;
            color: #666;
            border-bottom: 1px solid #e5e5e5;
        }}
        td {{
            padding: 0.75rem;
            border-bottom: 1px solid #f0f0f0;
        }}
        tr:hover {{
            background: #f9f9f9;
        }}
        .session-link {{
            color: #0066ff;
            text-decoration: none;
            font-weight: 500;
        }}
        .session-link:hover {{
            text-decoration: underline;
        }}
        .status-badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .status-badge.success {{ background: #00cc88; color: white; }}
        .status-badge.failed {{ background: #ff3333; color: white; }}
        .status-badge.running {{ background: #ffcc00; color: black; }}
        .status-badge.unknown {{ background: #999; color: white; }}
        .empty-state {{
            text-align: center;
            padding: 3rem;
            color: #999;
        }}
        .generated-at {{
            text-align: center;
            color: #999;
            font-size: 0.875rem;
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 1px solid #e5e5e5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Osiris Session Logs</h1>
            <p class="subtitle">Pipeline execution monitoring and analysis</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_sessions}</div>
                <div class="stat-label">Total Sessions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{success_rate:.0f}%</div>
                <div class="stat-label">Success Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{successful}</div>
                <div class="stat-label">Successful</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_rows:,}</div>
                <div class="stat-label">Total Rows Processed</div>
            </div>
        </div>

        <div class="sessions-section">
            {generate_sessions_html(session_types) if sessions else '<div class="empty-state">No sessions found</div>'}
        </div>

        <div class="generated-at">
            Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>"""

    # Write index page
    index_file = output_dir / "index.html"
    index_file.write_text(html)


def main(logs_dir: str, output_dir: str):
    """Generate multi-page HTML report from session logs."""
    logs_path = Path(logs_dir)
    output_path = Path(output_dir)

    if not logs_path.exists():
        print(f"Error: Logs directory '{logs_dir}' does not exist")
        sys.exit(1)

    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    # Read data.json
    data_file = output_path / "data.json"
    if not data_file.exists():
        print("Warning: data.json not found. Scanning logs directory...")
        sessions = []
        # Scan logs directory for session folders
        for session_dir in sorted(logs_path.iterdir()):
            if session_dir.is_dir() and not session_dir.name.startswith("."):
                session_id = session_dir.name
                sessions.append(
                    {
                        "session_id": session_id,
                        "status": "unknown",
                        "started_at": "",
                        "finished_at": "",
                        "duration_ms": 0,
                        "steps_ok": 0,
                        "steps_total": 0,
                        "rows_in": 0,
                        "rows_out": 0,
                        "errors": 0,
                        "warnings": 0,
                        "pipeline_name": None,
                    }
                )
    else:
        with open(data_file) as f:
            data = json.load(f)
            sessions = data.get("sessions", [])

    # Generate individual session pages
    for session in sessions:
        session_id = session["session_id"]
        logs = read_session_logs(logs_dir, session_id)
        generate_session_page(session, logs, output_path)

    # Generate index page
    generate_index_page(sessions, output_path)

    print(f"Multi-page HTML report generated in {output_dir}/")
    print(f"  - Index page: {output_dir}/index.html")
    print(f"  - {len(sessions)} session pages generated")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_multipage.py <logs_dir> <output_dir>")
        print("Example: python generate_multipage.py logs dist/logs")
        sys.exit(1)

    main(sys.argv[1], sys.argv[2])
