"""Copy the installed Claude Desktop archives into the work directory.

    python scripts/extract.py --work ~/.cache/claude-desktop-zh

Read-only: nothing under /usr is modified here.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import asar  # noqa: E402


def pristine(live: Path) -> Path:
    """Return the newest pristine backup of `live`, or `live` when there is none."""
    candidates = sorted(live.parent.glob(live.name + ".orig-*"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else live


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--app", type=Path,
                    default=Path(os.environ.get("CLAUDE_DESKTOP_DIR", "/usr/lib/claude-desktop")))
    args = ap.parse_args()

    resources = args.app / "resources"
    for name in ("app.asar", "ion-dist.asar"):
        if not (resources / name).is_file():
            raise SystemExit(f"missing {resources / name} - is Claude Desktop installed there?")

    args.work.mkdir(parents=True, exist_ok=True)
    for src, dest in (("app.asar", "app"), ("ion-dist.asar", "ion")):
        # always build on top of a pristine archive: if this machine already has
        # a patched install, the *.orig-* backup is the real baseline
        origin = pristine(resources / src)
        print(f"extracting {origin.name} ...", flush=True)
        asar.extract(origin, args.work / "extract" / dest)

    # keep pristines for restore.sh
    backup = args.work / "backup"
    backup.mkdir(exist_ok=True)
    for name in ("app.asar", "ion-dist.asar"):
        target = backup / name
        if not target.exists():
            shutil.copy2(resources / name, target)
            if (Path(str(resources / name) + ".unpacked")).is_dir():
                shutil.copytree(str(resources / name) + ".unpacked",
                                str(target) + ".unpacked", dirs_exist_ok=True)

    version = (args.app / "version")
    if version.is_file():
        print("app version:", version.read_text().strip())
    print("done ->", args.work / "extract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
