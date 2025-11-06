"""
Self-test module for Osiris MCP server.

Exercises handshake and basic tool calls for health verification.
"""

import asyncio
import json
import logging
import sys
import time

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)


async def run_selftest() -> bool:
    """
    Run MCP server self-test.

    Tests:
    1. Server handshake completes in <2 seconds
    2. connections.list tool responds successfully
    3. oml.schema.get tool responds with valid schema

    Returns:
        True if all tests pass, False otherwise
    """
    print("Starting MCP server self-test...")
    all_passed = True

    try:
        # Configure server parameters for stdio connection
        server_params = StdioServerParameters(command=sys.executable, args=["-m", "osiris.cli.mcp_entrypoint"])

        # Start timing
        start_time = time.time()

        # Connect to server
        async with stdio_client(server_params) as (read, write), ClientSession(read, write) as session:
            # Test 1: Handshake
            try:
                await asyncio.wait_for(session.initialize(), timeout=2.0)
                handshake_time = time.time() - start_time

                if handshake_time < 2.0:
                    print(f"✅ Handshake completed in {handshake_time:.3f}s (<2s requirement)")
                else:
                    print(f"❌ Handshake too slow: {handshake_time:.3f}s (>2s)")
                    all_passed = False

            except TimeoutError:
                print("❌ Handshake timeout (>2s)")
                return False

            # Test 2: connections.list tool
            try:
                result = await session.call_tool("connections.list", {})
                if result and hasattr(result, "content"):
                    # Parse the response
                    content = result.content[0]
                    if hasattr(content, "text"):
                        response = json.loads(content.text)
                        if response.get("status") == "success":
                            print("✅ connections.list responded successfully")
                        else:
                            print(f"❌ connections.list failed: {response}")
                            all_passed = False
                else:
                    print("❌ connections.list returned invalid response")
                    all_passed = False
            except Exception as e:
                print(f"❌ connections.list error: {e}")
                all_passed = False

            # Test 3: oml.schema.get tool
            try:
                result = await session.call_tool("oml.schema.get", {})
                if result and hasattr(result, "content"):
                    content = result.content[0]
                    if hasattr(content, "text"):
                        response = json.loads(content.text)
                        # Handle nested envelope format: {"status": "success", "result": {...}, "_meta": {...}}
                        payload = response.get("result", response)
                        if payload.get("version") == "0.1.0" and "schema" in payload:
                            print(f"✅ oml.schema.get returned valid schema (v{payload['version']})")
                        else:
                            print(f"❌ oml.schema.get invalid schema: {response}")
                            all_passed = False
                else:
                    print("❌ oml.schema.get returned invalid response")
                    all_passed = False
            except Exception as e:
                print(f"❌ oml.schema.get error: {e}")
                all_passed = False

            # Test 4: List tools to verify registration
            try:
                tools = await session.list_tools()
                if tools and hasattr(tools, "tools"):
                    tool_count = len(tools.tools)
                    tool_names = [t.name for t in tools.tools[:5]]
                    print(f"✅ Found {tool_count} registered tools")
                    print(f"   Sample tools: {tool_names}")
                else:
                    print("❌ Failed to list tools")
                    all_passed = False
            except Exception as e:
                print(f"❌ Tool listing error: {e}")
                all_passed = False

        # Summary
        total_time = time.time() - start_time
        print(f"\nSelf-test completed in {total_time:.3f}s")

        if all_passed:
            print("✅ All tests PASSED")
        else:
            print("❌ Some tests FAILED")

        return all_passed

    except Exception as e:
        print(f"❌ Self-test failed with error: {e}")
        import traceback  # noqa: PLC0415  # Lazy import for performance

        traceback.print_exc()
        return False


def main():
    """Main entry point for standalone self-test."""
    success = asyncio.run(run_selftest())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
