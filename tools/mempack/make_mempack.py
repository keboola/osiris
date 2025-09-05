#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

import yaml

BANNER = "=" * 80
FILE_BEGIN = "===== FILE BEGIN ====="
FILE_END = "===== FILE END ====="


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def iter_paths(root: Path, patterns: list[str], excludes: list[str]) -> list[Path]:
    # Expand include globs relative to repo root, filter with excludes, sort
    paths: set[Path] = set()
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file():
                paths.add(p.resolve())
    ex: set[Path] = set()
    for pat in excludes:
        for p in root.glob(pat):
            if p.exists():
                ex.add(p.resolve())
                if p.is_dir():
                    for sub in p.rglob("*"):
                        ex.add(sub.resolve())
    final = [p for p in paths if p not in ex]
    final.sort()
    return final


def build_tree(root: Path) -> str:
    # Compact “tree” without external deps; directories first, then files (sorted)
    lines = []
    for base, dirs, files in os.walk(root):
        # Skip .git and excluded junk implicitly (already handled by config excludes for files)
        rel = os.path.relpath(base, root)
        if rel == ".":
            rel = ""
        lines.append(rel + "/")
        for d in sorted(dirs):
            lines.append(os.path.join(rel, d) + "/")
        for f in sorted(files):
            lines.append(os.path.join(rel, f))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", "-c", default="tools/mempack/mempack.yaml")
    ap.add_argument("--root", "-r", default=".")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    out_path = Path(cfg.get("output", "./mempack.txt")).resolve()
    include = cfg.get("include", [])
    exclude = cfg.get("exclude", [])
    embed_tree = bool(cfg.get("embed_tree", True))
    notes = cfg.get("notes", "").strip()
    max_bytes = int(cfg.get("max_bytes", 0))

    files = iter_paths(root, include, exclude)

    # Collect file chunks deterministically
    chunks = []
    file_digests = []
    total_bytes = 0

    for p in files:
        rel = p.relative_to(root).as_posix()
        data = p.read_bytes()
        digest = sha256_bytes(data)
        file_digests.append({"path": rel, "sha256": digest, "bytes": len(data)})

        header = f"{FILE_BEGIN}\nPATH: {rel}\nSHA256: {digest}\n"
        footer = f"{FILE_END}\n"
        chunk = header + "\n" + p.read_text(encoding="utf-8", errors="replace") + "\n" + footer
        total_bytes += len(chunk.encode("utf-8"))
        chunks.append(chunk)

    # Overall digest to detect pack drift
    manifest_json = json.dumps(file_digests, sort_keys=True).encode("utf-8")
    overall_digest = sha256_bytes(manifest_json)

    # Compose output
    buf = io.StringIO()
    buf.write(f"{BANNER}\nOSIRIS MEMPACK\n{BANNER}\n")
    buf.write(f"GeneratedAt: {time.strftime('%Y-%m-%d %H:%M:%S %z')}\n")
    buf.write(f"RepoRoot: {root}\n")
    buf.write(f"OverallSHA256: {overall_digest}\n")
    buf.write(f"FilesCount: {len(files)}\n")
    buf.write(f"{BANNER}\n\n")

    if notes:
        buf.write("NOTES:\n")
        buf.write(notes + "\n\n" + BANNER + "\n\n")

    if embed_tree:
        buf.write("PROJECT TREE (relative paths):\n")
        buf.write(BANNER + "\n")
        buf.write(build_tree(root) + "\n")
        buf.write(BANNER + "\n\n")

    buf.write("FILE MANIFEST:\n")
    buf.write(json.dumps(file_digests, indent=2, sort_keys=True))
    buf.write("\n\n" + BANNER + "\n\n")

    for chunk in chunks:
        buf.write(chunk)
        buf.write("\n")

    out_bytes = buf.getvalue().encode("utf-8")
    if max_bytes and len(out_bytes) > max_bytes:
        print(
            f"[ERROR] mempack would be {len(out_bytes)} bytes, exceeds max_bytes={max_bytes}",
            file=sys.stderr,
        )
        sys.exit(2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)
    print(f"[OK] Wrote {out_path} ({len(out_bytes)} bytes) with {len(files)} files")
    print(f"[OK] OverallSHA256 = {overall_digest}")


if __name__ == "__main__":
    main()
