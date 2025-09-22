# Documentation Adjustments Summary

## 1. ADR-0027 Renamed and Updated
| Item | Change | Status |
|------|--------|--------|
| **Filename** | `0027-run-export.md` → `0027-run-export-context-for-AI.md` | ✅ Renamed |
| **Title** | "Run Export Bundle" → "Run Export Context for AI" | ✅ Updated |
| **Emphasis** | Added emphasis on AI-friendly context enrichment, not just plain text export | ✅ Enhanced |
| **Content** | Highlighted schemas, config context, and explanatory metadata | ✅ Updated |

## 2. ADR-0028 Adjusted
| Item | Change | Status |
|------|--------|--------|
| **Time Estimates** | Removed all week/month estimates | ✅ Removed |
| **Implementation Plan** | Changed from time-based to phase-based | ✅ Updated |
| **Goal Emphasis** | Highlighted reproducible environments: clone + secrets = restored | ✅ Enhanced |

## 3. ADRs 0001-0026 Status Updates

### Summary by Status
| Status | Count | ADRs |
|--------|-------|------|
| **Implemented** | 14 | 0001, 0002, 0003, 0004, 0006, 0011, 0012, 0013, 0014, 0015, 0019, 0020, 0025, 0026 |
| **Accepted** | 7 | 0005, 0007, 0008, 0009, 0021, 0022, 0023 |
| **Proposed** | 4 | 0016, 0017, 0018, 0024 |
| **Superseded** | 1 | 0010 (by ADR-0026) |

### Detailed Status Changes
| ADR | Title | Previous Status | New Status | Rationale |
|-----|-------|-----------------|------------|-----------|
| 0001 | Logging Configuration | Missing/Accepted | **Implemented** | Session logging fully implemented |
| 0002 | Discovery Cache Fingerprinting | Missing | **Implemented** | SHA-256 fingerprinting complete |
| 0003 | Session-Scoped Logging | Accepted | **Implemented** | Session directories working |
| 0004 | Configuration Precedence | Missing/Accepted | **Implemented** | CLI > ENV > YAML working |
| 0005 | Component Spec & Registry | Proposed | **Accepted** | Specs exist, partial impl |
| 0006 | Pipeline Runner | Accepted | **Implemented** | Runner v0 operational |
| 0007 | Component Capabilities | Proposed | **Accepted** | Capabilities in specs |
| 0008 | Component Registry | Proposed | **Accepted** | Registry exists |
| 0009 | Secrets Handling | Accepted | **Accepted** | Partial implementation |
| 0010 | E2B Integration | Accepted | **Superseded** | Replaced by ADR-0026 |
| 0011 | Roadmap | Proposed | **Implemented** | M0-M1 complete |
| 0012 | Separate Extractors/Writers | Accepted | **Implemented** | Components separated |
| 0013 | Chat Retry Policy | Accepted | **Implemented** | Retry mechanism works |
| 0014 | OML v0.1.0 | Accepted | **Implemented** | Schema enforced |
| 0015 | Compile Contract | Accepted | **Implemented** | Deterministic compilation |
| 0019 | Chat FSM | Accepted | **Implemented** | State machine active |
| 0020 | Connection Resolution | Accepted | **Implemented** | Connection management working |
| 0025 | CLI UX Unification | Proposed | **Implemented** | `run` + `logs` commands |
| 0026 | E2B Transparent Proxy | Accepted | **Implemented** | Proxy architecture complete |

## 4. Developer Guide - Discovery Mode
| Item | Change | Status |
|------|--------|--------|
| **New File** | `docs/developer-guide/discovery.md` | ✅ Created |
| **Content** | Discovery mode for interactive agents | ✅ Added |
| **Sections** | Purpose, Technical Contract, Examples, Best Practices | ✅ Complete |

## 5. Milestones M2-M4 Time Estimates Removed
| Milestone | Previous Timeline | New Timeline | Status |
|-----------|------------------|--------------|--------|
| **M2 - Scheduling** | Week-based (10 weeks) | Phase-based (5 phases) | ✅ Updated |
| **M3 - Technical Scale** | Month-based (4 months) | Phase-based (4 phases) | ✅ Updated |
| **M4 - DWH Agent** | Quarter-based (1 year) | Stage-based (4 stages) | ✅ Updated |

## Summary Statistics

### Files Modified: 31
- **ADRs Updated**: 26 files (status normalization)
- **ADRs Renamed**: 1 file (ADR-0027)
- **Milestones Updated**: 3 files (M2, M3, M4)
- **New Documentation**: 1 file (discovery.md)

### Status Distribution After Updates
- **54% Implemented** (14 ADRs): Core functionality complete
- **27% Accepted** (7 ADRs): Approved, partial or pending implementation
- **15% Proposed** (4 ADRs): Future features
- **4% Superseded** (1 ADR): Replaced by newer design

### Key Improvements
1. ✅ All ADR statuses normalized and accurate
2. ✅ ADR-0027 properly emphasizes AI context enrichment
3. ✅ ADR-0028 focuses on reproducibility without time estimates
4. ✅ Discovery mode documented for component developers
5. ✅ All milestone timelines converted from duration to sequence

---
*Documentation cleanup completed on milestone-m1 branch*
*Date: 2025-01-19*
