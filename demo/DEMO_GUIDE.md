# Multi-Source Activation Pipeline Simulator - Demo Guide

## Quick Start

```bash
# Navigate to demo directory
cd demo

# Install dependencies (if needed)
pip install typer rich pyyaml

# Run the full interactive pipeline
python interactive_demo.py

# Or use the CLI
python cli.py start
```

## What You'll See

The demo simulates a sophisticated data pipeline with:

1. **Interactive Prompts** - Approvals at key decision points
2. **Beautiful Terminal UI** - Rich formatting with colors and tables
3. **Realistic Processing** - Timed steps that feel authentic
4. **Professional Artifacts** - Real files generated in `out/` directory

## Demo Flow (12 minutes)

### Phase 1: Initialization
- System components introduction
- Requirements capture (90+ day lapsed customers)
- **USER APPROVAL**: Execution plan

### Phase 2: Data Preparation
- Connection verification (detects missing Shopify)
- Automatic connector generation from documentation
- Data discovery across 5 sources (2.8M records)

### Phase 3: Processing
- Identity resolution (185K identities, 84% merge rate)
- Feature engineering (RFM, churn scores, topics)
- Segmentation (3 segments, 54.7K customers)

### Phase 4: Quality & Compliance
- Data quality checks (4 rules, 1 warning)
- Privacy compliance (EU zone, PII masking)
- **USER APPROVAL**: Activation plan

### Phase 5: Activation & Publishing
- Channel configuration (Google Ads, ESP)
- Holdout groups (10%) and frequency caps
- Iceberg table publishing
- Artifact generation

## Generated Artifacts

All artifacts are created in the `out/` directory:

### 1. OML.yaml
Complete pipeline definition with:
- Multi-source extraction configs
- Identity resolution logic
- Feature engineering SQL
- Segmentation rules
- Privacy settings

### 2. activation_plan.json
```json
{
  "audiences": [
    {
      "name": "lapsed90",
      "size": 42000,
      "holdout": 0.10
    }
  ],
  "frequency_cap_per_week": 3
}
```

### 3. DQ_report.json
Data quality validation results with pass/warn/fail status

### 4. index.html
Beautiful HTML report with:
- Interactive charts (Chart.js)
- Pipeline flow diagrams (Mermaid)
- Metrics dashboard
- Collapsible artifact viewers

### 5. RunReport.md
Executive summary in markdown format

## Presentation Tips

### For Live Demo
1. **Clear the terminal first** for best visual impact
2. **Have the demo directory ready** with dependencies installed
3. **Run `python interactive_demo.py`** for best control
4. **Pause at approval points** to explain what's happening
5. **Show generated HTML report** in browser after completion

### For Quick Showcase
Use the simplified version for faster demonstration:
```bash
python run_demo.py  # 30-second version with all visuals
```

### Key Talking Points
- "Notice the automatic detection of the missing Shopify connector"
- "The identity resolution achieves 84% merge rate across 185K identities"
- "One schema drift warning on Mixpanel - new utm_campaign field"
- "10% holdout for A/B testing, 3/week frequency cap for user experience"
- "Everything is deterministic with seed 42 for reproducible results"

## Customization

### Adjust Timing
Edit wait times in `interactive_demo.py`:
```python
time.sleep(2)  # Reduce to 0.5 for faster demo
```

### Change Metrics
Modify values in step functions:
```python
segments = [
    ("lapsed90", 42000),  # Change segment sizes
    ("lapsed_vip", 4200),
]
```

### Add More Sources
Extend the sources list in discovery step

## Architecture Highlights

- **No external dependencies** - Completely self-contained
- **Deterministic execution** - Same results every run (seed=42)
- **Production aesthetics** - Looks and feels real
- **Modular design** - Easy to extend or modify

## Troubleshooting

### Import Errors
```bash
# Ensure you're in demo directory
cd demo

# Install dependencies
pip install typer rich pyyaml
```

### No Output Visible
The UI might be capturing output. Try:
```bash
python interactive_demo.py  # Best for interaction
python run_demo.py         # Simpler output
```

### Files Not Generated
Check the `out/` directory:
```bash
ls -la out/
# Should see: OML.yaml, activation_plan.json, etc.
```

## Performance Notes

- **Full run**: ~12 minutes (realistic timing)
- **Fast mode**: ~30 seconds (run_demo.py)
- **Memory usage**: Minimal (no real data processing)
- **CPU usage**: Low (mostly sleep timers)

## Integration Example

After the demo, show how to use generated artifacts:

```python
# This is what production code would look like
from osiris import Pipeline

# Load the generated pipeline
pipeline = Pipeline.from_oml("out/OML.yaml")

# Apply activation configuration
pipeline.activate("out/activation_plan.json")

# Execute the pipeline
pipeline.run()
```

## Summary

This simulator provides a convincing demonstration of a sophisticated data pipeline system without any real infrastructure. Perfect for:
- Product demos
- Investor presentations
- Technical showcases
- Training sessions

The terminal experience feels professional and real, with no indication it's a simulation. All generated artifacts are valid and production-ready formats.