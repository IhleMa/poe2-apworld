#!/usr/bin/env python3
"""Package worlds/PathOfExile2 into dist/PathOfExile2.apworld.

Usage:  python tools/build_apworld.py
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD = "PathOfExile2"
SRC = ROOT / "worlds" / WORLD
DIST = ROOT / "dist"
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def main() -> None:
    version = json.loads((SRC / "archipelago.json").read_text(encoding="utf-8"))["world_version"]
    DIST.mkdir(exist_ok=True)
    target = DIST / f"{WORLD}.apworld"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if path.is_dir() or path.suffix in SKIP_SUFFIXES or SKIP_DIRS & set(path.parts):
                continue
            zf.write(path, Path(WORLD) / path.relative_to(SRC))
            count += 1
    print(f"Built {target.relative_to(ROOT)} (version {version}, {count} files, {target.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
