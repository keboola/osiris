# Multi-Source Activation Pipeline Simulator

A self-contained terminal experience that simulates a real data/AI pipeline for reactivating lapsed customers across multiple data sources with identity resolution, feature engineering, segmentation, data quality checks, and activation orchestration.

## Features

- **Multi-Source Integration**: Supabase, Stripe, Mixpanel, Shopify, Zendesk
- **Identity Resolution**: Graph-based deterministic and probabilistic matching
- **Feature Engineering**: RFM scoring, churn prediction, topic modeling
- **Smart Segmentation**: Lapsed 90-day, Lapsed VIP, High churn risk
- **Data Quality Guardian**: Schema validation, business rules, drift detection
- **Privacy Compliance**: EU data zone, PII masking, consent management
- **Activation Orchestration**: Google Ads, ESP integration with holdout groups
- **Beautiful Terminal UX**: 3-pane layout with Rich formatting
- **Polished HTML Reports**: Interactive charts, Mermaid diagrams, metrics

## Installation

```bash
# Clone the repository
git clone <repository>
cd demo

# Install dependencies
pip install typer rich pyyaml
```

## Usage

### Start Full Pipeline

Run the complete pipeline flow with interactive approvals:

```bash
python cli.py start
```

This will:
1. Initialize the pipeline system
2. Capture objectives (90+ day lapsed reactivation)
3. Propose execution plan (requires approval)
4. Check connections and build missing connectors
5. Perform data discovery with PII masking
6. Execute identity resolution
7. Run feature engineering (RFM, churn scores, topics)
8. Build segments
9. Validate data quality
10. Create activation plan (requires approval)
11. Publish to Iceberg
12. Generate reports and artifacts

### Replay Pipeline

Replay from a specific checkpoint:

```bash
# Replay from activation step
python cli.py replay --from activation --speed fast

# Available speeds: fast, normal, slow
```

### Manage Checkpoints

List and navigate checkpoints:

```bash
# List available checkpoints
python cli.py checkpoint --list

# Go to specific checkpoint
python cli.py checkpoint --goto identity_resolution
```

### Mode Options

```bash
# Offline mode (default) - no network calls
python cli.py start --offline

# Online mode - shows additional banners (still simulated)
python cli.py start --online
```

## Generated Artifacts

After completion, find these artifacts in the `out/` directory:

### OML.yaml
Complete pipeline definition in Osiris Markup Language v0.1.0 format with:
- Multi-source extraction configurations
- Identity resolution logic
- Feature engineering SQL
- Segmentation rules
- DQ validation rules
- Activation configurations
- Privacy settings

### activation_plan.json
Detailed activation configuration including:
- 3 audience segments with sizes
- 10% holdout groups
- Frequency caps (3/week)
- Channel schedules
- Creative hints based on topics

### DQ_report.json
Data quality validation results:
- Null ratio checks
- Uniqueness validations
- Schema drift detection
- Business rule compliance

### RunReport.md
Concise markdown summary of the pipeline execution

### index.html
Beautiful HTML report featuring:
- Overview metrics dashboard
- Pipeline flow diagram (Mermaid)
- Segment analysis charts (Chart.js)
- Data quality pie chart
- Activation sequence diagram
- Collapsible artifact viewers
- Integration code snippets

## Key Features

### Terminal UX
- **3-Pane Layout**: Log stream, status panel, preview/artifacts
- **Real-time Updates**: Streaming logs with icons and colors
- **Progress Indicators**: Spinners for long operations
- **Hotkeys**: Enter (approve), Ctrl+Shift+D (preview), H (help)

### Deterministic Simulation
- Fixed seed (42) for reproducible outputs
- Consistent timing and metrics
- Stable artifact generation
- Predictable checkpoint behavior

### Privacy & Compliance
- Automatic PII masking in previews
- EU data zone enforcement
- Consent validation
- GDPR-compliant processing

## Architecture

```
demo/
├── cli.py                 # Main CLI entry point (Typer)
├── ui/
│   └── tui.py            # Terminal UI with Rich
├── scripts/
│   ├── fake_orchestrator.py    # State machine
│   ├── render_oml.py           # OML generator
│   └── build_html_report.py    # HTML report builder
├── assets/
│   ├── *.csv             # Sample data fixtures
│   ├── duckdb/*.sql      # SQL transformations
│   └── context7_*.md     # Documentation for connector builder
├── generated/            # Runtime generated code
├── out/                 # Pipeline artifacts
└── state/              # Execution state
```

## Development

The simulator is designed to be:
- **Completely offline**: No external dependencies or network calls
- **Deterministic**: Same results every run (seed=42)
- **Extensible**: Easy to add new sources, segments, or features
- **Realistic**: Mimics real pipeline behavior and timing

## Performance

- **Full execution**: ~9-12 minutes in normal mode
- **Fast replay**: <90 seconds from activation to finish
- **Memory efficient**: Simulated data, no large datasets
- **Responsive UI**: 4fps refresh rate, smooth animations

## Integration

After pipeline completion, use the generated artifacts:

```python
# Example integration code
from osiris import Pipeline

# Load the generated pipeline
pipeline = Pipeline.from_oml("out/OML.yaml")

# Apply activation configuration
pipeline.activate("out/activation_plan.json")

# Run the pipeline
pipeline.run()
```

## License

MIT