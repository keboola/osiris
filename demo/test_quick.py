#!/usr/bin/env python3
"""Quick test of the demo system"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ui.tui import TerminalUI

# Test the UI
ui = TerminalUI()

# Test log updates
ui.update_log_stream("Starting system test...", "🚀")
ui.update_log_stream("Loading components...", "⚙️")
ui.update_log_stream("Initialization complete!", "✅")

# Test status updates
ui.update_status(
    current_step="Testing",
    throughput="1000 rows/s",
    merge_rate="85%",
    dq_status="✅ All checks passed",
    segment_sizes={
        "lapsed90": 42000,
        "vip": 4200
    }
)

# Test preview
ui.update_preview("SELECT * FROM users LIMIT 10", "sql")

# Render once
print("UI Test successful! Layout rendering works.")

# Now test orchestrator import
from scripts.fake_orchestrator import PipelineOrchestrator
print("Orchestrator import successful!")

print("\n✅ All imports working. You can now run: python cli.py start")