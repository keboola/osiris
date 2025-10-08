#!/usr/bin/env python3
"""Migration script to strip algorithm prefixes from manifest_hash in run index.

This script processes .osiris/index/runs.jsonl and all per-pipeline index files,
removing any 'sha256:' or similar prefixes from manifest_hash fields.

Usage:
    python scripts/migrate_index_manifest_hash.py                    # Dry run
    python scripts/migrate_index_manifest_hash.py --apply            # Apply changes
    python scripts/migrate_index_manifest_hash.py --index-dir PATH   # Custom index location
"""

import argparse
import json
import shutil
import sys
from pathlib import Path


def normalize_hash(hash_str: str) -> str:
    """Normalize manifest hash by removing algorithm prefix."""
    if not hash_str:
        return hash_str

    # Handle 'algo:hash' format
    if ":" in hash_str:
        return hash_str.split(":", 1)[1]

    # Handle 'algohash' format (e.g., 'sha256abc123')
    if hash_str.startswith("sha256") and len(hash_str) > 6:
        remainder = hash_str[6:]
        if all(c in "0123456789abcdef" for c in remainder.lower()):
            return remainder

    return hash_str


def migrate_jsonl_file(file_path: Path, dry_run: bool = True) -> tuple[int, int]:
    """Migrate a single JSONL file.

    Args:
        file_path: Path to JSONL file
        dry_run: If True, don't write changes

    Returns:
        Tuple of (total_records, modified_records)
    """
    if not file_path.exists():
        return 0, 0

    total = 0
    modified = 0
    new_lines = []

    with open(file_path) as f:
        for line in f:
            if not line.strip():
                new_lines.append(line)
                continue

            total += 1
            record = json.loads(line)

            # Check if manifest_hash needs normalization
            old_hash = record.get("manifest_hash", "")
            new_hash = normalize_hash(old_hash)

            if old_hash != new_hash:
                record["manifest_hash"] = new_hash
                # Also update manifest_short if it was derived from prefixed hash
                if record.get("manifest_short", "").startswith("sha256"):
                    record["manifest_short"] = new_hash[:7] if new_hash else ""
                modified += 1

            # Write record back
            new_lines.append(json.dumps(record, separators=(",", ":")) + "\n")

    # Write changes if not dry run
    if not dry_run and modified > 0:
        # Create backup
        backup_path = file_path.with_suffix(".bak")
        shutil.copy2(file_path, backup_path)

        # Write updated content
        with open(file_path, "w") as f:
            f.writelines(new_lines)

    return total, modified


def main():
    parser = argparse.ArgumentParser(
        description="Migrate manifest_hash in run index to pure hex format (no algorithm prefix)"
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path(".osiris/index"),
        help="Index directory (default: .osiris/index)",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry run)")
    args = parser.parse_args()

    index_dir = args.index_dir
    dry_run = not args.apply

    if not index_dir.exists():
        print(f"❌ Index directory not found: {index_dir}")
        sys.exit(1)

    print("🔍 Manifest Hash Migration")
    print(f"Index directory: {index_dir}")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY CHANGES'}")
    print()

    # Collect all JSONL files to migrate
    files_to_migrate = []

    # Main index
    main_index = index_dir / "runs.jsonl"
    if main_index.exists():
        files_to_migrate.append(("Main index", main_index))

    # Per-pipeline indexes
    by_pipeline_dir = index_dir / "by_pipeline"
    if by_pipeline_dir.exists():
        for pipeline_file in sorted(by_pipeline_dir.glob("*.jsonl")):
            pipeline_name = pipeline_file.stem
            files_to_migrate.append((f"Pipeline: {pipeline_name}", pipeline_file))

    if not files_to_migrate:
        print("✅ No index files found. Nothing to migrate.")
        return

    # Process files
    total_records = 0
    total_modified = 0

    for desc, file_path in files_to_migrate:
        records, modified = migrate_jsonl_file(file_path, dry_run)
        total_records += records
        total_modified += modified

        if modified > 0:
            status = "Would modify" if dry_run else "Modified"
            print(f"  {status}: {desc} ({modified}/{records} records)")
        elif records > 0:
            print(f"  ✓ {desc} ({records} records, no changes needed)")

    print()
    print("📊 Summary")
    print(f"  Total records: {total_records}")
    print(f"  Records with prefixed hashes: {total_modified}")

    if dry_run and total_modified > 0:
        print()
        print("💡 Run with --apply to write changes")
        print("   Backup files will be created with .bak extension")
    elif not dry_run and total_modified > 0:
        print()
        print("✅ Migration complete!")
        print("   Backup files saved with .bak extension")
    elif total_modified == 0:
        print()
        print("✅ All manifest hashes are already in pure hex format. No migration needed.")


if __name__ == "__main__":
    main()
