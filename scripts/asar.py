"""Minimal ASAR helper: extract / pack via the @electron/asar CLI, plus a fast
header reader used to verify that unpacked entries survive a repack.
"""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
from pathlib import Path

ASAR_CLI = ["npx", "--yes", "@electron/asar"]


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract(asar: Path, dest: Path) -> None:
    """Extract an archive into `dest` (replacing it)."""
    if dest.exists():
        shutil.rmtree(dest)
    _run(ASAR_CLI + ["extract", str(asar), str(dest)])
    # Files listed as "unpacked" live next to the archive, not inside it.
    unpacked = Path(str(asar) + ".unpacked")
    if unpacked.is_dir():
        shutil.copytree(unpacked, dest, dirs_exist_ok=True)


def pack(src: Path, dest: Path, unpack_glob: str | None = None) -> None:
    """Pack `src` into `dest`; keep native/exec bits out of the archive body."""
    if dest.exists():
        dest.unlink()
    shutil.rmtree(str(dest) + ".unpacked", ignore_errors=True)
    args = ASAR_CLI + ["pack", str(src), str(dest)]
    if unpack_glob:
        args += ["--unpack", unpack_glob]
    _run(args)


def unpacked_entries(asar: Path) -> list[str]:
    with open(asar, "rb") as f:
        # 4 x uint32: pickle size, header pickle size, header string size, json length
        json_len = struct.unpack("<4I", f.read(16))[3]
        header = json.loads(f.read(json_len))
    out: list[str] = []

    def walk(node: dict, prefix: str = "") -> None:
        for name, entry in node.get("files", {}).items():
            path = f"{prefix}/{name}"
            if "files" in entry:
                walk(entry, path)
            elif entry.get("unpacked"):
                out.append(path)

    walk(header)
    return out
