# Milestone M1d: Logs Browser v1

**Status**: ✅ Complete  
**Date**: January 2025  
**Version**: v0.2.0  

## Overview

Implemented a static, offline HTML logs browser for viewing Osiris session logs through a web interface. This provides an intuitive visual way to explore session history, timelines, and details without requiring external tools or servers.

## Deliverables

### 1. ✅ Static HTML Generator (`tools/logs_report/generate.py`)
- Single-file HTML output with inline CSS/JavaScript
- No external dependencies or build chain required
- Works from `file://` URLs (offline capable)
- Generates both index view and single-session views
- Deterministic JSON data generation using SessionReader

### 2. ✅ CLI Integration
- **`osiris logs html`** - Generate static HTML report
  - `--out DIR` - Output directory (default: `dist/logs`)
  - `--open` - Open in browser after generation
  - `--sessions N` - Limit number of sessions
  - `--since DATE` - Filter by date
  - `--label NAME` - Filter by label
  - `--status STATUS` - Filter by status
- **`osiris logs open`** - Generate and open single-session HTML
  - Accepts session ID, "last", or `--label NAME`
  - Automatically opens in default browser

### 3. ✅ Timeline Visualization
- Canvas-based timeline rendering (no external libraries)
- Visual representation of session duration and status
- Interactive hover details
- Color-coded by status (green=success, red=failed, yellow=running)

### 4. ✅ Deprecation Shims
- Legacy `osiris runs` commands now redirect to `osiris logs`
- Shows deprecation warnings per ADR-0025
- Maintains backward compatibility during transition

### 5. ✅ Tests
- `test_cli_html.py` - CLI command tests
- `test_html_generation.py` - HTML generation tests
- Coverage for filters, edge cases, and deprecation paths

## Implementation Details

### Architecture
```
tools/logs_report/
  generate.py         # HTML generation logic
  
osiris/cli/
  logs.py            # CLI commands + deprecation shims
  main.py            # Command routing updates

tests/logs/
  test_cli_html.py   # CLI tests
  test_html_generation.py # Generation tests
```

### Key Features
1. **Single-file SPA**: Complete HTML application in one file
2. **Offline capable**: No server or internet required
3. **Deep linking**: `index.html#session=<id>` support
4. **Responsive design**: Works on mobile and desktop
5. **Fast filtering**: Client-side filtering for instant response

### Technology Choices
- **No frameworks**: Pure HTML/CSS/JavaScript for simplicity
- **Canvas API**: Native browser API for timeline visualization
- **Inline everything**: CSS and JS embedded for portability
- **JSON data**: Reuses existing SessionReader and serializers

## Acceptance Criteria

### ✅ Functional Requirements
- [x] Generate static HTML report from session logs
- [x] Support filtering by status, label, time
- [x] Timeline visualization using canvas
- [x] Deep linking to specific sessions
- [x] Single-session view generation
- [x] Works from file:// URLs

### ✅ Non-Functional Requirements
- [x] No external dependencies (self-contained)
- [x] No build toolchain required
- [x] Deterministic output (reproducible)
- [x] Fast generation (<1s for 100 sessions)
- [x] Browser compatible (Chrome, Firefox, Safari)

### ✅ Migration Path
- [x] Deprecation warnings for `osiris runs` commands
- [x] Clear migration guide in help text
- [x] Backward compatibility maintained

## Usage Examples

```bash
# Generate HTML report
osiris logs html

# Generate and open immediately
osiris logs html --open

# Filter to recent successes
osiris logs html --status success --since 2025-01-01

# Open specific session
osiris logs open session_001

# Open last session
osiris logs open last

# Open session by label
osiris logs open --label production
```

## Testing

```bash
# Run all logs tests
pytest tests/logs/

# Run HTML generation tests
pytest tests/logs/test_html_generation.py

# Run CLI tests
pytest tests/logs/test_cli_html.py

# Test deprecation shims
osiris runs list  # Should show warning
```

## Related ADRs

- **ADR-0025**: CLI UX Unification - Defines deprecation strategy for `runs` → `logs`
- **ADR-0021**: Session-scoped logging - Provides the data model we visualize
- **ADR-0023**: Log commands - Original specification for log management

## Next Steps

### M1e Enhancements (Future)
- Search functionality in HTML interface
- Export to PDF capability
- Comparison view for multiple sessions
- Performance metrics charts
- Real-time updates (WebSocket support)

### M2 Integration
- Link to compiled manifests viewer
- Connection topology visualization
- Error analysis dashboard
- Pipeline lineage tracking

## Verification

Run the following to verify the implementation:

```bash
# 1. Generate sample sessions
python osiris.py chat  # Create some sessions

# 2. Generate HTML report
osiris logs html --open

# 3. Test single session
osiris logs open last

# 4. Test deprecation
osiris runs list  # Should warn

# 5. Run tests
pytest tests/logs/test_cli_html.py -v
pytest tests/logs/test_html_generation.py -v
```

## Changelog

### Added
- Static HTML report generator with timeline visualization
- CLI commands: `logs html` and `logs open`
- Deprecation shims for legacy `runs` commands
- Comprehensive test coverage for HTML generation

### Changed
- Updated `main.py` to route new commands
- Enhanced `logs.py` with HTML generation functions

### Technical Debt
- Consider extracting HTML template to separate file (future)
- Add caching for repeated HTML generation
- Optimize for very large session counts (1000+)
