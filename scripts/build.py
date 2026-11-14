"""Build patched Claude Desktop archives with a Simplified Chinese UI.

    python scripts/build.py --work ~/.cache/claude-desktop-zh [--app /usr/lib/claude-desktop]

Reads the archives extracted by `extract.py`, then writes:
    <work>/out/app.asar
    <work>/out/app.asar.unpacked/
    <work>/out/ion-dist.asar

What gets patched
  1. i18n/zh-Hans.json (+ i18n/dynamic/zh-Hans.json) - every English string
     replaced by its translation, missing translations fall back to English.
  2. The renderer's locale allow-lists ("en-US","de-DE",...,"id-ID") gain
     "zh-Hans", so the language picker offers 中文（简体） and system detection
     resolves zh / zh-CN / zh-Hans to it.
  3. The main process' system-language map gains zh -> zh-Hans.
  4. The shell locale catalog gets the keys the shipped stub is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import asar  # noqa: E402

LOCALES = '["en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID"]'
LOCALES_ZH = '["en-US","zh-Hans","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID"]'
UNPACK_GLOB = "{*.node,github-mcp-server}"


def load_cache(work: Path) -> dict[str, str]:
    cache: dict[str, str] = {}
    path = work / "cache.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            cache[row["s"]] = row["t"]
    return cache


def rewrite(path: Path, old: str, new: str, what: str, required: bool = True) -> bool:
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if old not in text:
        if required:
            raise SystemExit(f"anchor for {what} not found in {path} (unsupported app version?)")
        print(f"  ! {what}: anchor missing, skipped")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8", errors="surrogateescape")
    print(f"  + {what}: {path.name}")
    return True


def patch_locale_lists(ion: Path) -> None:
    """Add zh-Hans to every hard-coded locale allow-list in the renderer bundle."""
    hits = 0
    for js in (ion / "assets").rglob("*.js"):
        text = js.read_text(encoding="utf-8", errors="surrogateescape")
        if LOCALES_ZH in text and LOCALES not in text:
            print(f"  = locale allow-list already patched: {js.name}")
            hits += 1
            continue
        if LOCALES not in text:
            continue
        js.write_text(text.replace(LOCALES, LOCALES_ZH), encoding="utf-8", errors="surrogateescape")
        hits += text.count(LOCALES)
        print(f"  + locale allow-list: {js.name}")
    if hits == 0:
        raise SystemExit("no locale allow-list found in the renderer bundle")


def patch_main_locale_map(app: Path) -> None:
    """Teach the main process that zh* means zh-Hans."""
    chunk = None
    for js in (app / ".vite/build").glob("*.js"):
        if '{en:"en-US",de:"de-DE"' in js.read_text(encoding="utf-8", errors="surrogateescape"):
            chunk = js
            break
    if chunk is None:
        raise SystemExit("system-language map not found in the main bundle")
    if '"zh-Hans":"zh-Hans"' in chunk.read_text(encoding="utf-8", errors="surrogateescape"):
        print(f"  = main-process locale map already patched: {chunk.name}")
        return
    rewrite(chunk, '{en:"en-US",de:"de-DE"',
            '{en:"en-US",zh:"zh-Hans","zh-Hans":"zh-Hans",de:"de-DE"',
            "main-process locale map")


def build_catalogs(app: Path, ion: Path, cache: dict[str, str]) -> None:
    tr = cache.get

    shell_en = json.loads((app / "resources/i18n/en-US.json").read_text(encoding="utf-8"))
    shell_path = app / "resources/i18n/zh-Hans.json"
    shell_zh = json.loads(shell_path.read_text(encoding="utf-8")) if shell_path.exists() else {}
    added = 0
    for key, value in shell_en.items():
        if key not in shell_zh:
            shell_zh[key] = tr(value, value)
            added += 1
    shell_path.write_text(json.dumps(shell_zh, ensure_ascii=False, indent=2, sort_keys=True),
                          encoding="utf-8")
    print(f"  + shell catalog: {len(shell_zh)} keys ({added} added)")

    for name, rel in (("", "i18n/en-US.json"), ("/dynamic", "i18n/dynamic/en-US.json")):
        source = json.loads((ion / rel).read_text(encoding="utf-8"))
        target = {k: tr(v, v) for k, v in source.items()}
        out = ion / rel.replace("en-US", "zh-Hans")
        out.write_text(json.dumps(target, ensure_ascii=False), encoding="utf-8")
        translated = sum(1 for k, v in source.items() if target[k] != v)
        label = "spa catalog" if not name else "spa dynamic catalog"
        print(f"  + {label}: {len(target)} keys, {translated} translated")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--app", type=Path,
                    default=Path(os.environ.get("CLAUDE_DESKTOP_DIR", "/usr/lib/claude-desktop")))
    args = ap.parse_args()

    extract = args.work / "extract"
    app, ion = extract / "app", extract / "ion"
    if not (app / ".vite/build").is_dir() or not (ion / "i18n").is_dir():
        raise SystemExit(f"run extract.py first: {extract} is missing the extracted archives")

    cache = load_cache(args.work)
    print(f"translations in cache: {len(cache)}")

    build_catalogs(app, ion, cache)
    patch_locale_lists(ion)
    patch_main_locale_map(app)

    # Bytecode cache for the files we edited would be stale; drop it and let
    # Electron recompile on first launch.
    for cached in (app / "compile-cache").glob("*.jsc"):
        cached.unlink()

    out = args.work / "out"
    out.mkdir(parents=True, exist_ok=True)
    asar.pack(app, out / "app.asar", UNPACK_GLOB)
    asar.pack(ion, out / "ion-dist.asar")

    kept = asar.unpacked_entries(out / "app.asar")
    if not kept:
        raise SystemExit("repacked app.asar lost its unpacked entries (*.node) - aborting")
    print(f"packed: {out/'app.asar'} ({os.path.getsize(out/'app.asar')/1e6:.1f} MB), "
          f"{out/'ion-dist.asar'} ({os.path.getsize(out/'ion-dist.asar')/1e6:.1f} MB)")
    print("unpacked entries kept:", ", ".join(p.lstrip("/") for p in kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
