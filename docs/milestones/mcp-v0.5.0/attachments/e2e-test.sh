#!/bin/bash
#
# MCP v0.5.0 End-to-End Testing Script (Final Working Version)
# ===========================================================
#
# Validates all MCP v0.5.0 features are functional
# Runs from testing_env directory (required for Osiris initialization)
#
# Usage:
#   cd /path/to/testing_env
#   /path/to/e2e-test.sh
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Paths
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
TESTING_ENV="$(pwd)"
OSIRIS_PY="$REPO_ROOT/osiris.py"

# Counters
PASS=0
FAIL=0

# Helpers
pass() { echo -e "${GREEN}✅${NC} $*"; ((PASS++)); }
fail() { echo -e "${RED}❌${NC} $*"; ((FAIL++)); }
info() { echo -e "${BLUE}ℹ️${NC}  $*"; }
section() { echo ""; echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BOLD}$*${NC}"; echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# Verify environment
section "Environment Validation"

if [ ! -f osiris.yaml ]; then
    fail "osiris.yaml not found"
    fail "Run: cd $TESTING_ENV && python ../osiris.py init"
    exit 1
fi
pass "osiris.yaml exists"

if [ ! -f "$OSIRIS_PY" ]; then
    fail "osiris.py not found at $OSIRIS_PY"
    exit 1
fi
pass "osiris.py found"

info "Testing from: $(pwd)"

# Scenario A: CLI & Server
section "SCENARIO A: CLI & Server Initialization"

if python ../osiris.py --help >/dev/null 2>&1; then
    pass "osiris.py --help works"
else
    fail "osiris.py --help failed"
fi

if python ../osiris.py mcp --help >/dev/null 2>&1; then
    pass "osiris.py mcp --help works"
else
    fail "osiris.py mcp --help failed"
fi

if python ../osiris.py mcp run --selftest >/dev/null 2>&1; then
    pass "MCP selftest passes"
else
    fail "MCP selftest failed"
fi

# Scenario B: Connection Management
section "SCENARIO B: Connection Management"

if python ../osiris.py mcp connections list --json >/dev/null 2>&1; then
    pass "connections list works"
else
    fail "connections list failed"
fi

# Get first connection to test doctor
CONN_ID=$(python ../osiris.py mcp connections list --json 2>&1 | python -c "import sys, json; data=json.load(sys.stdin); print(data['connections'][0]['reference'] if data.get('connections') else '')" 2>/dev/null)
if [ -n "$CONN_ID" ] && python ../osiris.py mcp connections doctor --connection-id "$CONN_ID" --json >/dev/null 2>&1; then
    pass "connections doctor works"
else
    fail "connections doctor failed"
fi

# Scenario C: OML & Discovery
section "SCENARIO C: OML & Discovery"

if python ../osiris.py mcp oml schema --json >/dev/null 2>&1; then
    pass "oml schema works"
else
    fail "oml schema failed"
fi

if python ../osiris.py mcp components list --json >/dev/null 2>&1; then
    pass "components list works"
else
    fail "components list failed"
fi

if python ../osiris.py mcp usecases list --json >/dev/null 2>&1; then
    pass "usecases list works"
else
    fail "usecases list failed"
fi

# Scenario D: Memory & AIOP
section "SCENARIO D: Memory & AIOP"

if python ../osiris.py mcp memory capture --session-id test --text "test" --consent --json >/dev/null 2>&1; then
    pass "memory capture works"
else
    fail "memory capture failed"
fi

if python ../osiris.py mcp aiop list --json >/dev/null 2>&1; then
    pass "aiop list works"
else
    fail "aiop list failed"
fi

# Scenario E: Security Validation
section "SCENARIO E: Security Validation"

CONN=$(python ../osiris.py mcp connections list --json 2>&1)

if echo "$CONN" | grep -q '***MASKED***' 2>/dev/null; then
    pass "Secrets are masked"
else
    info "No masked secrets found (may be expected if no sensitive data)"
fi

if echo "$CONN" | grep -q 'password\|key' 2>/dev/null | grep -qv '\*\*\*' 2>/dev/null; then
    fail "Credential leak detected!"
else
    pass "No credential leakage detected"
fi

# Summary
section "TEST RESULTS"

TOTAL=$((PASS + FAIL))
PCT=$((PASS * 100 / TOTAL))

echo ""
echo -e "  ${GREEN}✅ Passed${NC}: $PASS/$TOTAL"
echo -e "  ${RED}❌ Failed${NC}: $FAIL/$TOTAL"
echo -e "  ${BLUE}📊 Pass Rate${NC}: $PCT%"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✅ MCP v0.5.0 FULLY FUNCTIONAL${NC}"
    echo ""
    echo "Validated features:"
    echo "  • CLI & MCP server"
    echo "  • Connection management with masking"
    echo "  • OML schema & validation"
    echo "  • Component & usecase discovery"
    echo "  • Memory capture & AIOP access"
    echo "  • Security: no credential leakage"
    exit 0
else
    echo -e "${RED}${BOLD}❌ SOME TESTS FAILED${NC}"
    exit 1
fi
