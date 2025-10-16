#!/bin/bash
# Local test script for Phase 1 CI guards
# Tests the same logic as .github/workflows/mcp-phase1-guards.yml

set -e

echo "🧪 Testing Phase 1 CI Guards Locally"
echo "===================================="
echo ""

# Test 1: Forbidden Imports
echo "1️⃣  Testing Forbidden Imports Check..."
echo "----------------------------------------"

FORBIDDEN_FILES=$(grep -r \
  -E "resolve_connection|load_connections_yaml|parse_connection_ref|_load_connections" \
  osiris/mcp/tools/*.py \
  2>/dev/null \
  | grep -v "^#" \
  | grep -v "# noqa" \
  || true)

if [ -n "$FORBIDDEN_FILES" ]; then
  echo "❌ FORBIDDEN IMPORTS DETECTED!"
  echo "$FORBIDDEN_FILES"
  exit 1
fi

echo "✅ No forbidden imports found"
echo ""

# Test 2: Config Format Validation
echo "2️⃣  Testing Config Format Validation..."
echo "----------------------------------------"

python -c "
import yaml
import sys
from pathlib import Path

config_file = Path('testing_env/osiris.yaml')
if not config_file.exists():
    print('⚠️  testing_env/osiris.yaml not found')
    sys.exit(0)

with open(config_file) as f:
    config = yaml.safe_load(f)

errors = []
fs = config.get('filesystem', {})

base_path = fs.get('base_path', '')
if not base_path:
    errors.append('filesystem.base_path is empty')
elif not Path(base_path).is_absolute():
    errors.append(f'filesystem.base_path is not absolute: {base_path}')

mcp_logs_dir = fs.get('mcp_logs_dir', '')
if not mcp_logs_dir:
    errors.append('filesystem.mcp_logs_dir is missing')

if errors:
    print('❌ Config validation FAILED:')
    for error in errors:
        print(f'   - {error}')
    sys.exit(1)

print('✅ Config format valid')
print(f'   base_path: {base_path}')
print(f'   mcp_logs_dir: {mcp_logs_dir}')
" || exit 1

echo ""

# Test 3: osiris init generates valid config
echo "3️⃣  Testing osiris init Config Generation..."
echo "----------------------------------------"

TEMP_DIR=$(mktemp -d)
echo "   Test directory: $TEMP_DIR"

python osiris.py init "$TEMP_DIR" --force > /dev/null 2>&1

python -c "
import yaml
import sys
from pathlib import Path

config_file = Path('$TEMP_DIR/osiris.yaml')
with open(config_file) as f:
    config = yaml.safe_load(f)

fs = config.get('filesystem', {})
base_path = fs.get('base_path', '')
mcp_logs_dir = fs.get('mcp_logs_dir', '')

if not Path(base_path).is_absolute():
    print(f'❌ Generated base_path not absolute: {base_path}')
    sys.exit(1)

if mcp_logs_dir != '.osiris/mcp/logs':
    print(f'❌ Generated mcp_logs_dir incorrect: {mcp_logs_dir}')
    sys.exit(1)

print('✅ osiris init generates valid config')
print(f'   Generated base_path: {base_path}')
" || exit 1

rm -rf "$TEMP_DIR"
echo ""

# Test 4: MCP clients output
echo "4️⃣  Testing MCP Clients Output..."
echo "----------------------------------------"

cd testing_env
OUTPUT=$(python ../osiris.py mcp clients --json 2>&1)

if echo "$OUTPUT" | grep -q "osiris.py mcp run\|mcp_entrypoint"; then
  echo "✅ MCP clients output contains correct command"
else
  echo "❌ MCP clients output missing 'osiris.py mcp run'"
  exit 1
fi

cd ..
echo ""

# Test 5: Base path resolution
echo "5️⃣  Testing Base Path Resolution..."
echo "----------------------------------------"

python -c "
import sys
import os
from pathlib import Path

sys.path.insert(0, os.getcwd())

from osiris.mcp.config import MCPFilesystemConfig
import tempfile
import yaml

temp_dir = Path(tempfile.mkdtemp())
config_file = temp_dir / 'osiris.yaml'

config = {
    'version': '2.0',
    'filesystem': {
        'base_path': str(temp_dir),
        'mcp_logs_dir': '.osiris/mcp/logs'
    }
}

with open(config_file, 'w') as f:
    yaml.dump(config, f)

fs_config = MCPFilesystemConfig.from_config(str(config_file))

assert fs_config.base_path == temp_dir.resolve()
assert fs_config.mcp_logs_dir == (temp_dir / '.osiris' / 'mcp' / 'logs').resolve()

print('✅ Base path resolution works correctly')

import shutil
shutil.rmtree(temp_dir)
" || exit 1

echo ""
echo "===================================="
echo "✅ All Phase 1 CI Guards PASSED"
echo "===================================="
echo ""
echo "Summary:"
echo "  ✓ No forbidden imports in MCP tools"
echo "  ✓ Config format validation passes"
echo "  ✓ osiris init generates valid config"
echo "  ✓ MCP clients output correct"
echo "  ✓ Base path resolution functional"
echo ""
