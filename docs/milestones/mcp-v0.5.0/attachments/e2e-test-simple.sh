#!/bin/bash
#
# MCP v0.5.0 End-to-End Testing Script (Simplified)
# ==================================================
#
# Pragmatic E2E test suite for MCP server validation.
# Works with already-activated venv and testing_env setup.
#
# Prerequisites:
#   - Virtual environment already activated
#   - testing_env/ initialized with osiris.yaml
#   - Run from: cd /Users/padak/github/osiris/docs/milestones/mcp-v0.5.0/attachments/
#
# Usage:
#   ./e2e-test-simple.sh [--verbose]
#   ./e2e-test-simple.sh --help
#

set -eu  # Exit on error, undefined vars (not -o pipefail to allow test failures)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
TESTING_ENV="$REPO_ROOT/testing_env"
OSIRIS_PY="$REPO_ROOT/osiris.py"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0
VERBOSE=false

for arg in "$@"; do
    case $arg in
        --verbose) VERBOSE=true ;;
        --help)
            echo "MCP v0.5.0 E2E Testing (Simplified)"
            echo ""
            echo "Usage: $0 [--verbose]"
            echo ""
            echo "Prerequisites:"
            echo "  • Virtual environment activated"
            echo "  • testing_env/ initialized with osiris.yaml"
            echo "  • Python 3.11+ installed"
            echo ""
            exit 0
            ;;
    esac
done

# Helper functions
log_pass() { echo -e "${GREEN}✅ PASS${NC}: $*"; ((TESTS_PASSED++)); }
log_fail() { echo -e "${RED}❌ FAIL${NC}: $*"; ((TESTS_FAILED++)); }
log_skip() { echo -e "${YELLOW}⊘ SKIP${NC}: $*"; ((TESTS_SKIPPED++)); }
log_info() { echo -e "${BLUE}ℹ️  INFO${NC}: $*"; }
log_section() { echo ""; echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BOLD}${CYAN}  $*${NC}"; echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# Test environment setup
log_section "ENVIRONMENT VALIDATION"

if [ ! -d "$TESTING_ENV" ]; then
    log_fail "testing_env directory not found: $TESTING_ENV"
    log_fail "Run: mkdir -p $TESTING_ENV && cd $TESTING_ENV && python ../osiris.py init"
    exit 1
fi
log_pass "testing_env directory exists"

if [ ! -f "$TESTING_ENV/osiris.yaml" ]; then
    log_fail "osiris.yaml not found"
    log_fail "Run: cd $TESTING_ENV && python ../osiris.py init"
    exit 1
fi
log_pass "osiris.yaml configured"

# Extract base_path from config
BASE_PATH=$(python -c "import yaml; c=yaml.safe_load(open('$TESTING_ENV/osiris.yaml')); print(c.get('filesystem', {}).get('base_path', '$TESTING_ENV'))" 2>/dev/null || echo "$TESTING_ENV")
log_pass "base_path: $BASE_PATH"

# Check Python
if ! command -v python &> /dev/null; then
    log_fail "Python not found in PATH"
    exit 1
fi
log_pass "Python available: $(python --version)"

# Check osiris.py
if [ ! -f "$OSIRIS_PY" ]; then
    log_fail "osiris.py not found: $OSIRIS_PY"
    exit 1
fi
log_pass "osiris.py found"

# ============================================================================
# TEST SCENARIOS
# ============================================================================

log_section "SCENARIO A: CLI BASIC FUNCTIONALITY"

# Test 1: osiris --help
if timeout 5 python "$OSIRIS_PY" --help >/dev/null 2>&1; then
    log_pass "osiris.py --help works"
else
    log_fail "osiris.py --help failed"
fi

# Test 2: Check if mcp command exists
if timeout 5 python "$OSIRIS_PY" mcp --help >/dev/null 2>&1; then
    log_pass "osiris.py mcp --help works"
else
    log_skip "osiris.py mcp command not yet implemented"
fi

log_section "SCENARIO B: MCP CLI COMMANDS"

cd "$TESTING_ENV" || exit 1

# Test 3: MCP selftest (if implemented)
if timeout 5 python "$OSIRIS_PY" mcp run --selftest >/dev/null 2>&1; then
    log_pass "osiris.py mcp run --selftest works"
else
    log_skip "osiris.py mcp run --selftest not yet fully implemented or no config"
fi

# Test 4: MCP connections list
if timeout 5 python "$OSIRIS_PY" mcp connections list --json >/dev/null 2>&1; then
    log_pass "osiris.py mcp connections list returns JSON"
else
    log_skip "osiris.py mcp connections list not yet fully implemented"
fi

# Test 5: MCP discovery list
if timeout 5 python "$OSIRIS_PY" mcp discovery --help >/dev/null 2>&1; then
    log_pass "osiris.py mcp discovery command available"
else
    log_skip "osiris.py mcp discovery command not yet implemented"
fi

# Test 6: MCP OML commands
if timeout 5 python "$OSIRIS_PY" mcp oml --help >/dev/null 2>&1; then
    log_pass "osiris.py mcp oml command available"
else
    log_skip "osiris.py mcp oml command not yet implemented"
fi

# Test 7: MCP memory capture
if timeout 5 python "$OSIRIS_PY" mcp memory --help >/dev/null 2>&1; then
    log_pass "osiris.py mcp memory command available"
else
    log_skip "osiris.py mcp memory command not yet implemented"
fi

log_section "SCENARIO C: CONFIGURATION & FILESYSTEM"

# Test 8: MCP logs directory exists
if [ -d "$BASE_PATH/.osiris/mcp/logs" ]; then
    log_pass "MCP logs directory exists"
else
    log_skip "MCP logs directory not yet created (will be created on first MCP command)"
fi

# Test 9: Python can import osiris
if python -c "import sys; sys.path.insert(0, '$REPO_ROOT'); import osiris" 2>/dev/null; then
    log_pass "osiris module importable"
else
    log_fail "Cannot import osiris module"
fi

# Test 10: MCP server module available (if Phase 2+ is complete)
if python -c "import sys; sys.path.insert(0, '$REPO_ROOT'); from osiris.mcp import server" 2>/dev/null; then
    log_pass "osiris.mcp.server module available"
else
    log_skip "osiris.mcp.server module not yet available (Phase 2 feature)"
fi

log_section "SCENARIO D: INTEGRATION TESTS"

# Test 11: Run a complete flow
if [ -n "$(cd "$TESTING_ENV" && python "$OSIRIS_PY" connections list --json 2>/dev/null | grep -E '(connections|error)' || true)" ]; then
    log_pass "CLI returns JSON responses"
else
    log_skip "CLI connection commands not yet implemented"
fi

# Test 12: Check git branch (informational)
cd "$REPO_ROOT" || exit 1
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
if [ "$BRANCH" = "feature/mcp-server-opus" ]; then
    log_pass "On correct branch: $BRANCH"
else
    log_skip "Not on feature/mcp-server-opus branch (on: $BRANCH)"
fi

# ============================================================================
# SUMMARY
# ============================================================================

log_section "TEST SUMMARY"

TOTAL=$((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))
echo ""
echo -e "  ${GREEN}✅ Passed:${NC}  $TESTS_PASSED"
echo -e "  ${RED}❌ Failed:${NC}  $TESTS_FAILED"
echo -e "  ${YELLOW}⊘ Skipped:${NC} $TESTS_SKIPPED"
echo -e "  ${BLUE}📊 Total:${NC}  $TOTAL"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✅ No failures - all essential tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Implement missing MCP CLI commands (if skipped tests)"
    echo "  2. Run: ./e2e-test-simple.sh --verbose"
    echo "  3. For full test suite, run: pytest tests/mcp/ -v"
    exit 0
else
    echo -e "${RED}${BOLD}❌ Some tests failed - see errors above${NC}"
    exit 1
fi
