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

## Data Engineer Assessment & Enhancements

### Investigation Results (Sep 2025)
After examining the current implementation against actual session data (`run_1757461848561`), identified critical gaps for data engineering workflows:

**Current State:**
- ✅ Basic overview with session grouping
- ✅ Clickable links to session details
- ❌ **Broken event display** - only shows "INFO" levels without timestamps/messages
- ❌ **Useless metrics** - raw numbers (2138, 1.31) without context/units
- ❌ **Missing execution context** - no indication of E2B remote vs local runs
- ❌ **Missing critical data** - no artifacts, logs, pipeline steps

**Rich Data Available:**
```json
// Events with structured data
{"event":"e2b.prepare.start", "ts":"2025-09-09T23:50:48.562968+00:00"}
{"event":"e2b.upload.finish", "duration":2.916, "sandbox_id":"unknown"}

// Metrics with proper units
{"metric":"e2b.payload.size", "value":2138, "unit":"bytes"}
{"metric":"e2b.exec.duration", "value":1.31, "unit":"seconds"}

// Files: artifacts/, osiris.log, metadata.json, build/
```

### M1d+ Priority Enhancements (Data Engineer Tool)

#### Overview Page Improvements
- [x] **E2B execution badges** - Orange "E2B" indicator for remote runs
- [x] **Duration column** - Show execution times (5.8s, 1.3s)
- [x] **Column headers** - Clear headers with sticky positioning when scrolling
- [x] **Row counts per session** - Data throughput visibility
- [x] **Table structure** - Proper HTML table with clickable rows
- [ ] **Pipeline names** - Extract from session metadata
- [ ] **Sortable table** - By date, duration, status, rows
- [ ] **Search/filter bar** - Quick session lookup

#### Detail Page New Tabs
- [ ] **Pipeline Steps** - Mermaid flow diagram with timings
- [x] **Artifacts** - File browser for artifacts/, build/, remote/
- [ ] **Technical Logs** - osiris.log viewer with syntax highlighting  
- [ ] **Metadata** - Execution context, environment details
- [ ] **Performance** - Metrics dashboard with proper units

#### Fixed Core Issues
- [x] **Fix Events tab** - Show timestamps, messages, structured data
- [x] **Fix Metrics tab** - Display with units, formatted values
- [ ] **Add log streaming** - Access to debug.log, osiris.log content

### Implementation Approach
Keep "raw" data engineer tool aesthetic:
- **No fancy UI** - Focus on data visibility
- **Mermaid diagrams** - For pipeline visualization
- **Monospace fonts** - For technical content
- **Fast implementation** - Minimal CSS, direct HTML generation
- **Tabular data** - Sortable tables for analysis

### Implementation Progress (January 2025)

#### Completed Enhancements
1. **Fixed Events Tab**
   - Proper timestamp formatting (HH:MM:SS.mmm)
   - Event names displayed correctly
   - Structured data shown with key=value pairs
   - Color coding for E2B events

2. **Fixed Metrics Tab**
   - Unit-aware formatting (2.1KB instead of 2138)
   - Duration formatting (1.31s instead of 1.31)
   - Color coding by metric type

3. **E2B Execution Badges**
   - Orange badges on overview page
   - Automatic detection via metadata.json or e2b.* events
   - Visual distinction for remote executions

4. **Duration Column**
   - Added to overview page
   - Smart formatting (ms, s, m based on value)
   - Grid layout for better alignment

5. **Artifacts Tab**
   - Complete file browser implementation
   - Directory tree with nested files
   - File type icons (📁 📄 📋 📊 📝)
   - Size formatting (bytes, KB, MB)

6. **Table Structure with Headers**
   - Proper HTML table layout
   - Column headers (Session ID, Started, Duration, Rows, Status)
   - Sticky headers when scrolling
   - Clickable rows for navigation

7. **Row Counts Display**
   - Data throughput visibility
   - Formatted with thousands separator
   - Shows "-" when no data processed

### Next Steps

### M1e Enhancements (Future)
- Export capabilities (CSV, JSON, logs)
- Session comparison view
- Performance trends over time
- Data lineage tracking

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
