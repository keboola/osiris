"""
Resource resolver for Osiris MCP server.

Maps Osiris URIs to actual resources and handles resource operations.
"""

import json
from pathlib import Path

from mcp import types
from pydantic import AnyUrl

from osiris.mcp.errors import ErrorFamily, OsirisError


class ResourceResolver:
    """
    Resolver for Osiris MCP resources.

    All resources are under the osiris://mcp/ namespace:
    - osiris://mcp/schemas/...  -> data/schemas/ (read-only)
    - osiris://mcp/prompts/...  -> data/prompts/ (read-only)
    - osiris://mcp/usecases/... -> data/usecases/ (read-only)
    - osiris://mcp/discovery/... -> state/discovery/cache/ (runtime)
    - osiris://mcp/drafts/...    -> state/drafts/ (runtime)
    - osiris://mcp/memory/...    -> state/memory/ (runtime)
    """

    def __init__(self, base_dir: Path | None = None):
        """
        Initialize the resource resolver.

        Args:
            base_dir: Base directory for MCP resources
        """
        self.base_dir = base_dir or Path(__file__).parent
        self.data_dir = self.base_dir / "data"
        self.state_dir = self.base_dir / "state"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _parse_uri(self, uri: str) -> tuple[str, Path]:
        """
        Parse an Osiris URI and return the resource type and path.

        Args:
            uri: Osiris URI (e.g., osiris://mcp/schemas/oml/v0.1.0.json)

        Returns:
            Tuple of (resource_type, relative_path)

        Raises:
            OsirisError: If URI is invalid
        """
        if not uri.startswith("osiris://mcp/"):
            raise OsirisError(
                ErrorFamily.SEMANTIC, f"Invalid URI scheme: {uri}", path=["uri"], suggest="Use osiris://mcp/... URIs"
            )

        # Remove prefix and split
        path_part = uri[len("osiris://mcp/") :]
        parts = path_part.split("/", 1)

        if len(parts) < 2:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Invalid URI format: {uri}",
                path=["uri"],
                suggest="Use format osiris://mcp/<type>/<path>",
            )

        resource_type = parts[0]
        relative_path = Path(parts[1])

        return resource_type, relative_path

    def _get_physical_path(self, uri: str) -> Path:
        """
        Get the physical file path for a URI.

        Args:
            uri: Osiris URI

        Returns:
            Physical file path

        Raises:
            OsirisError: If resource type is unknown
        """
        resource_type, relative_path = self._parse_uri(uri)

        # Map resource types to directories
        if resource_type in ["schemas", "prompts", "usecases"]:
            # Read-only data resources
            return self.data_dir / resource_type / relative_path
        elif resource_type in ["discovery", "drafts", "memory"]:
            # Runtime state resources
            return self.state_dir / resource_type / relative_path
        else:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Unknown resource type: {resource_type}",
                path=["uri", "type"],
                suggest="Valid types: schemas, prompts, usecases, discovery, drafts, memory",
            )

    async def list_resources(self) -> list[types.Resource]:
        """
        List all available resources.

        Returns:
            List of MCP Resource objects
        """
        resources = []

        # Add schema resources
        resources.append(
            types.Resource(
                uri=AnyUrl("osiris://mcp/schemas/oml/v0.1.0.json"),
                name="OML v0.1.0 Schema",
                description="JSON Schema for OML pipeline format version 0.1.0",
                mimeType="application/json",
            )
        )

        # Add prompt resources
        resources.append(
            types.Resource(
                uri=AnyUrl("osiris://mcp/prompts/oml_authoring_guide.md"),
                name="OML Authoring Guide",
                description="Guide for authoring OML pipelines",
                mimeType="text/markdown",
            )
        )

        # Add usecase resources
        resources.append(
            types.Resource(
                uri=AnyUrl("osiris://mcp/usecases/catalog.yaml"),
                name="Use Case Catalog",
                description="Catalog of OML pipeline use cases and templates",
                mimeType="application/x-yaml",
            )
        )

        return resources

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        """
        Read a resource by URI.

        Args:
            uri: Resource URI

        Returns:
            Resource content

        Raises:
            OsirisError: If resource not found or cannot be read
        """
        # Get physical path
        try:
            file_path = self._get_physical_path(uri)
        except OsirisError:
            raise

        # Check if file exists
        if not file_path.exists():
            # Check if it's a discovery artifact that should be generated
            if "discovery" in uri:
                return await self._generate_discovery_artifact(uri)

            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Resource not found: {uri}",
                path=["uri"],
                suggest="Check the resource URI or run discovery first",
            )

        # Read the file
        try:
            if file_path.suffix == ".json":
                with open(file_path) as f:
                    content = json.load(f)
                    text = json.dumps(content, indent=2)
            else:
                with open(file_path) as f:
                    text = f.read()

            return types.ReadResourceResult(contents=[types.TextContent(type="text", text=text)])

        except (OSError, json.JSONDecodeError) as e:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to read resource: {str(e)}",
                path=["uri"],
                suggest="Check resource permissions and format",
            )

    async def _generate_discovery_artifact(self, uri: str) -> types.ReadResourceResult:
        """
        Generate a discovery artifact on-demand.

        Args:
            uri: Discovery artifact URI

        Returns:
            Generated artifact content
        """
        # Parse discovery URI format: osiris://mcp/discovery/{disc_id}/{artifact}.json
        parts = uri.split("/")
        if len(parts) < 5:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Invalid discovery URI format: {uri}",
                path=["uri"],
                suggest="Use format osiris://mcp/discovery/<id>/<artifact>.json",
            )

        discovery_id = parts[3]
        artifact_name = parts[4].replace(".json", "")

        # Generate placeholder content based on artifact type
        if artifact_name == "overview":
            content = {
                "discovery_id": discovery_id,
                "timestamp": "2025-10-14T00:00:00Z",
                "connection": "unknown",
                "database": "unknown",
                "tables_count": 0,
                "total_rows": 0,
            }
        elif artifact_name == "tables":
            content = {"discovery_id": discovery_id, "tables": []}
        elif artifact_name == "samples":
            content = {"discovery_id": discovery_id, "samples": {}}
        else:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Unknown discovery artifact: {artifact_name}",
                path=["uri", "artifact"],
                suggest="Valid artifacts: overview, tables, samples",
            )

        return types.ReadResourceResult(contents=[types.TextContent(type="text", text=json.dumps(content, indent=2))])

    async def write_resource(self, uri: str, content: str) -> bool:
        """
        Write a resource (for runtime resources only).

        Args:
            uri: Resource URI
            content: Content to write

        Returns:
            True if successful

        Raises:
            OsirisError: If resource is read-only or write fails
        """
        resource_type, _ = self._parse_uri(uri)

        # Check if resource type is writable
        if resource_type in ["schemas", "prompts", "usecases"]:
            raise OsirisError(
                ErrorFamily.POLICY,
                f"Cannot write to read-only resource type: {resource_type}",
                path=["uri", "type"],
                suggest="Only discovery, drafts, and memory resources are writable",
            )

        # Get physical path and ensure parent directory exists
        file_path = self._get_physical_path(uri)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the content
        try:
            with open(file_path, "w") as f:
                f.write(content)
            return True
        except OSError as e:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to write resource: {str(e)}",
                path=["uri"],
                suggest="Check file permissions and disk space",
            )

    def validate_uri(self, uri: str) -> bool:
        """
        Validate that a URI follows the correct format.

        Args:
            uri: URI to validate

        Returns:
            True if valid
        """
        try:
            self._parse_uri(uri)
            return True
        except OsirisError:
            return False
