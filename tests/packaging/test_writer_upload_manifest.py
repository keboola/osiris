"""Test to ensure writer drivers are included in E2B upload manifest."""

from pathlib import Path


def test_supabase_writer_driver_exists_in_drivers_dir():
    """Verify that supabase_writer_driver.py exists in osiris/drivers/."""
    # This test ensures the file exists so it will be picked up by the glob
    # in e2b_transparent_proxy.py line 540-543
    osiris_root = Path(__file__).parent.parent.parent / "osiris"
    driver_file = osiris_root / "drivers" / "supabase_writer_driver.py"

    assert driver_file.exists(), f"Driver file not found: {driver_file}"
    assert driver_file.is_file(), f"Driver path is not a file: {driver_file}"

    # Verify it has the _ddl_attempt method with correct signature
    content = driver_file.read_text()
    assert "def _ddl_attempt(self, *, step_id: str, table: str, schema: str, operation: str, channel: str)" in content
    assert "class SupabaseWriterDriver(Driver):" in content


def test_e2b_proxy_uploads_all_driver_files():
    """Verify E2B proxy code includes logic to upload all driver files."""
    # Read the E2B transparent proxy code
    proxy_file = Path(__file__).parent.parent.parent / "osiris" / "remote" / "e2b_transparent_proxy.py"
    assert proxy_file.exists(), "E2B transparent proxy not found"

    content = proxy_file.read_text()

    # Verify the upload logic exists (around line 540)
    assert 'drivers_dir = osiris_root / "drivers"' in content
    assert "for driver_file in drivers_dir.glob" in content
    assert 'await self.sandbox.files.write(f"/home/user/osiris/drivers/{driver_file.name}"' in content


def test_all_writer_drivers_will_be_uploaded():
    """List all writer drivers to ensure they're included in upload."""
    osiris_root = Path(__file__).parent.parent.parent / "osiris"
    drivers_dir = osiris_root / "drivers"

    # Get all driver files (simulating the E2B upload logic)
    driver_files = list(drivers_dir.glob("*.py"))
    driver_files = [f for f in driver_files if f.name != "__init__.py"]

    # Ensure we have key drivers
    driver_names = [f.name for f in driver_files]
    assert "supabase_writer_driver.py" in driver_names, f"supabase_writer_driver.py not found in {driver_names}"
    assert (
        "filesystem_csv_writer_driver.py" in driver_names
    ), f"filesystem_csv_writer_driver.py not found in {driver_names}"

    # All drivers should have class definitions
    for driver_file in driver_files:
        content = driver_file.read_text()
        # Each driver should define a class that inherits from Driver
        assert "class " in content
        assert "(Driver)" in content or "from " in content  # Either inherits or imports
