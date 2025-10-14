"""
Test MCP server bootstrap and stdio communication.
"""

import asyncio
import json
import subprocess
import sys
import time
import pytest


class TestServerBoot:
    """Test MCP server boot and handshake."""

    @pytest.mark.asyncio
    async def test_server_handshake_stdio(self):
        """Test server handshake via stdio with Content-Length framing."""
        # Start server as subprocess
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "osiris.cli.mcp_entrypoint",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        try:
            # Prepare initialize request
            request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                },
                "id": 1
            }

            # Send with Content-Length framing
            request_str = json.dumps(request)
            request_bytes = request_str.encode('utf-8')
            header = f"Content-Length: {len(request_bytes)}\r\n\r\n"

            proc.stdin.write(header.encode('utf-8'))
            proc.stdin.write(request_bytes)
            await proc.stdin.drain()

            # Read response header
            start_time = time.time()
            header_line = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)

            # Verify Content-Length header
            assert header_line.startswith(b"Content-Length:")
            content_length = int(header_line.decode().split(":")[1].strip())

            # Skip empty line
            await proc.stdout.readline()

            # Read content
            response_bytes = await asyncio.wait_for(
                proc.stdout.read(content_length),
                timeout=2.0
            )

            elapsed = time.time() - start_time

            # Parse and verify response
            response = json.loads(response_bytes.decode('utf-8'))

            assert "result" in response
            assert response["id"] == 1

            result = response["result"]
            assert "protocolVersion" in result
            assert "capabilities" in result
            assert "serverInfo" in result

            # Check timing requirement
            assert elapsed < 2.0, f"Handshake took {elapsed:.3f}s (>2s)"

        finally:
            proc.terminate()
            await proc.wait()

    @pytest.mark.asyncio
    async def test_server_capabilities(self):
        """Test server reports correct capabilities."""
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "osiris.cli.mcp_entrypoint"]
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Verify capabilities
                assert hasattr(session, 'server_info')

                # List tools to verify capability
                tools = await session.list_tools()
                assert tools is not None
                assert hasattr(tools, 'tools')
                assert len(tools.tools) > 0

    def test_server_version(self):
        """Test server version matches configuration."""
        from osiris.mcp.config import MCPConfig

        config = MCPConfig()
        assert config.SERVER_VERSION == "0.5.0"
        assert config.PROTOCOL_VERSION == "0.5"