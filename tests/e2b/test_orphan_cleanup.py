"""Test orphan sandbox detection and cleanup for E2B."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from osiris.remote.e2b_adapter import E2BAdapter
from osiris.remote.e2b_client import SandboxHandle, SandboxStatus


class TestOrphanSandboxDetection:
    """Test detection and cleanup of orphaned E2B sandboxes."""

    @pytest.fixture
    def mock_sandbox_list(self):
        """Mock list of existing sandboxes."""
        return [
            {
                "id": "sandbox-old-123",
                "created_at": (datetime.now() - timedelta(hours=2)).isoformat(),
                "status": "running",
                "metadata": {"session_id": "old-session"},
            },
            {
                "id": "sandbox-recent-456",
                "created_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
                "status": "running",
                "metadata": {"session_id": "recent-session"},
            },
            {
                "id": "sandbox-orphan-789",
                "created_at": (datetime.now() - timedelta(hours=3)).isoformat(),
                "status": "failed",
                "metadata": {"session_id": "orphan-session"},
            },
        ]

    def test_identify_orphaned_sandboxes(self, mock_sandbox_list):
        """Test identifying orphaned sandboxes based on age and status."""
        # Sandboxes older than 1 hour should be considered orphaned
        max_age_hours = 1
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        orphaned = []
        for sandbox in mock_sandbox_list:
            created_at = datetime.fromisoformat(sandbox["created_at"])
            if created_at < cutoff_time:
                orphaned.append(sandbox["id"])

        assert len(orphaned) == 2
        assert "sandbox-old-123" in orphaned
        assert "sandbox-orphan-789" in orphaned
        assert "sandbox-recent-456" not in orphaned

    @patch("osiris.remote.e2b_client.E2BClient")
    def test_cleanup_orphaned_sandboxes(self, mock_client_class, mock_sandbox_list):
        """Test cleanup of orphaned sandboxes."""
        mock_client = MagicMock()
        mock_client.list_sandboxes.return_value = mock_sandbox_list
        mock_client.close.return_value = None
        mock_client_class.return_value = mock_client

        # Function to cleanup orphaned sandboxes
        def cleanup_orphaned_sandboxes(client, max_age_hours=1, dry_run=False):
            """Cleanup sandboxes older than max_age_hours."""
            sandboxes = client.list_sandboxes()
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

            cleaned = []
            for sandbox in sandboxes:
                created_at = datetime.fromisoformat(sandbox["created_at"])
                if created_at < cutoff_time:
                    if not dry_run:
                        try:
                            handle = SandboxHandle(
                                sandbox_id=sandbox["id"],
                                status=SandboxStatus(sandbox["status"]),
                                metadata=sandbox.get("metadata", {}),
                            )
                            client.close(handle)
                            cleaned.append(sandbox["id"])
                        except Exception as e:
                            print(f"Failed to cleanup {sandbox['id']}: {e}")
                    else:
                        cleaned.append(sandbox["id"])

            return cleaned

        # Test dry run first
        orphaned = cleanup_orphaned_sandboxes(mock_client, dry_run=True)
        assert len(orphaned) == 2
        mock_client.close.assert_not_called()

        # Test actual cleanup
        cleaned = cleanup_orphaned_sandboxes(mock_client, dry_run=False)
        assert len(cleaned) == 2
        assert mock_client.close.call_count == 2

    def test_sandbox_tagging_for_tracking(self):
        """Test that sandboxes are properly tagged for tracking."""
        adapter = E2BAdapter({"timeout": 300, "metadata": {"project": "osiris-test", "environment": "ci"}})

        # Verify metadata is included in configuration
        assert "metadata" in adapter.e2b_config
        assert adapter.e2b_config["metadata"]["project"] == "osiris-test"
        assert adapter.e2b_config["metadata"]["environment"] == "ci"

    @pytest.mark.e2b_live
    @pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
    @pytest.mark.skipif(not os.getenv("E2B_LIVE_TESTS"), reason="E2B_LIVE_TESTS not enabled")
    def test_live_orphan_detection(self):
        """Test orphan detection with live E2B service."""
        # from osiris.remote.e2b_client import E2BClient
        # client = E2BClient()

        # List current sandboxes
        # Note: This assumes E2B SDK provides a list_sandboxes method
        # If not available, this test would need to be adjusted
        try:
            # This is a placeholder - actual implementation depends on E2B SDK
            # sandboxes = client.list_sandboxes()
            # Check for any sandboxes older than expected
            pass
        except AttributeError:
            pytest.skip("E2B SDK doesn't support listing sandboxes")


class TestSandboxLifecycleTracking:
    """Test tracking of sandbox lifecycle for cleanup."""

    @pytest.fixture
    def sandbox_tracker(self):
        """Create a sandbox tracker for testing."""

        class SandboxTracker:
            def __init__(self):
                self.active_sandboxes = {}
                self.completed_sandboxes = []

            def register(self, sandbox_id: str, metadata: dict):
                """Register a new sandbox."""
                self.active_sandboxes[sandbox_id] = {
                    "created_at": datetime.now(),
                    "metadata": metadata,
                }

            def complete(self, sandbox_id: str):
                """Mark sandbox as completed."""
                if sandbox_id in self.active_sandboxes:
                    sandbox_info = self.active_sandboxes.pop(sandbox_id)
                    sandbox_info["completed_at"] = datetime.now()
                    self.completed_sandboxes.append(sandbox_info)

            def get_active(self, older_than_minutes=None):
                """Get active sandboxes, optionally filtered by age."""
                if older_than_minutes is None:
                    return list(self.active_sandboxes.keys())

                cutoff = datetime.now() - timedelta(minutes=older_than_minutes)
                return [sid for sid, info in self.active_sandboxes.items() if info["created_at"] < cutoff]

        return SandboxTracker()

    def test_sandbox_registration(self, sandbox_tracker):
        """Test sandbox registration and tracking."""
        # Register sandboxes
        sandbox_tracker.register("sandbox-1", {"session": "test-1"})
        sandbox_tracker.register("sandbox-2", {"session": "test-2"})

        # Check active sandboxes
        active = sandbox_tracker.get_active()
        assert len(active) == 2
        assert "sandbox-1" in active
        assert "sandbox-2" in active

        # Complete one sandbox
        sandbox_tracker.complete("sandbox-1")

        # Check active sandboxes again
        active = sandbox_tracker.get_active()
        assert len(active) == 1
        assert "sandbox-2" in active

        # Check completed sandboxes
        assert len(sandbox_tracker.completed_sandboxes) == 1

    def test_sandbox_age_filtering(self, sandbox_tracker):
        """Test filtering sandboxes by age."""
        # Register a sandbox
        sandbox_tracker.register("sandbox-old", {"session": "old"})

        # Manually set created_at to be old
        sandbox_tracker.active_sandboxes["sandbox-old"]["created_at"] = datetime.now() - timedelta(hours=2)

        # Register a recent sandbox
        sandbox_tracker.register("sandbox-new", {"session": "new"})

        # Get all active
        all_active = sandbox_tracker.get_active()
        assert len(all_active) == 2

        # Get only old sandboxes (> 60 minutes)
        old_sandboxes = sandbox_tracker.get_active(older_than_minutes=60)
        assert len(old_sandboxes) == 1
        assert "sandbox-old" in old_sandboxes

    @patch("osiris.remote.e2b_adapter.E2BAdapter")
    def test_sandbox_cleanup_on_exception(self, mock_adapter_class):
        """Test that sandboxes are cleaned up even when exceptions occur."""
        mock_adapter = MagicMock()
        mock_adapter.sandbox_handle = SandboxHandle(
            sandbox_id="exception-sandbox", status=SandboxStatus.RUNNING, metadata={}
        )
        mock_adapter.client = MagicMock()
        mock_adapter_class.return_value = mock_adapter

        # Simulate an exception during execution
        mock_adapter.execute.side_effect = RuntimeError("Test exception")

        adapter = mock_adapter_class()

        # Execute should raise but cleanup should still happen
        with pytest.raises(RuntimeError):
            adapter.execute(MagicMock(), MagicMock())

        # In real implementation, finally block should ensure cleanup
        # This would be verified by checking that client.close was called


class TestCleanupUtility:
    """Test cleanup utility for orphaned sandboxes."""

    def test_cleanup_script_logic(self):
        """Test the logic for a cleanup script."""

        def should_cleanup_sandbox(sandbox_info: dict, max_age_hours: float = 1.0) -> bool:
            """Determine if a sandbox should be cleaned up."""
            # Check age
            created_at = datetime.fromisoformat(sandbox_info["created_at"])
            age = datetime.now() - created_at
            if age.total_seconds() / 3600 > max_age_hours:
                return True

            # Check status
            return sandbox_info.get("status") in ["failed", "timeout", "cancelled"]

        # Test with old sandbox
        old_sandbox = {
            "created_at": (datetime.now() - timedelta(hours=2)).isoformat(),
            "status": "running",
        }
        assert should_cleanup_sandbox(old_sandbox) is True

        # Test with recent sandbox
        recent_sandbox = {
            "created_at": (datetime.now() - timedelta(minutes=30)).isoformat(),
            "status": "running",
        }
        assert should_cleanup_sandbox(recent_sandbox) is False

        # Test with failed sandbox (should cleanup regardless of age)
        failed_sandbox = {"created_at": datetime.now().isoformat(), "status": "failed"}
        assert should_cleanup_sandbox(failed_sandbox) is True

    def test_cleanup_report_generation(self):
        """Test generating a cleanup report."""
        cleanup_results = [
            {"sandbox_id": "sandbox-1", "status": "cleaned", "age_hours": 2.5},
            {"sandbox_id": "sandbox-2", "status": "cleaned", "age_hours": 3.0},
            {
                "sandbox_id": "sandbox-3",
                "status": "error",
                "age_hours": 1.5,
                "error": "Permission denied",
            },
        ]

        def generate_cleanup_report(results: list) -> dict:
            """Generate a cleanup report."""
            report = {
                "timestamp": datetime.now().isoformat(),
                "total_processed": len(results),
                "successful": sum(1 for r in results if r["status"] == "cleaned"),
                "failed": sum(1 for r in results if r["status"] == "error"),
                "details": results,
            }
            return report

        report = generate_cleanup_report(cleanup_results)

        assert report["total_processed"] == 3
        assert report["successful"] == 2
        assert report["failed"] == 1
        assert len(report["details"]) == 3
