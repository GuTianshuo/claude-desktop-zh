"""Translate every English UI string of the installed Claude Desktop into
Simplified Chinese, using a resumable on-disk cache.

    python scripts/run_translate.py --work ~/.cache/claude-desktop-zh

Only strings the app itself ships are processed, and nothing leaves the
machine unless you point OPENAI_BASE_URL at a remote endpoint.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import translate as tr  # noqa: E402


def load_corpus(work: Path) -> list[str]:
    """Unique English strings from the SPA catalog, its dynamic catalog and the
    desktop shell catalog (shell keys that already exist in zh are skipped)."""
    sources = [
        work / "extract/ion/i18n/en-US.json",
        work / "extract/ion/i18n/dynamic/en-US.json",
    ]
    seen: dict[str, None] = {}
    for path in sources:
        for value in json.loads(path.read_text(encoding="utf-8")).values():
            if isinstance(value, str):
                seen.setdefault(value, None)

    shell_en = json.loads((work / "extract/app/resources/i18n/en-US.json").read_text(encoding="utf-8"))
    shell_zh = json.loads((work / "extract/app/resources/i18n/zh-Hans.json").read_text(encoding="utf-8"))
    for key, value in shell_en.items():
        if key not in shell_zh and isinstance(value, str):
            seen.setdefault(value, None)

    # shortest first: buttons and menu labels get translated first
    return sorted(seen, key=lambda s: (len(s), s))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path, help="work directory holding extract/")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=tr.BATCH)
    args = ap.parse_args()

    cache_path = args.work / "cache.jsonl"
    cache: dict[str, str] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            cache[row["s"]] = row["t"]

    corpus = load_corpus(args.work)
    todo = [s for s in corpus if s not in cache and tr.looks_translatable(s)]
    skip = [s for s in corpus if s not in cache and not tr.looks_translatable(s)]
    print(f"corpus={len(corpus)} cached={len(cache)} todo={len(todo)} verbatim={len(skip)}", flush=True)

    lock = threading.Lock()
    done = [0]
    out = cache_path.open("a", encoding="utf-8")

    def work(batch: list[str]) -> None:
        results = tr.translate(batch)
        with lock:
            for src, dst in zip(batch, results):
                value = dst if tr.valid(src, dst) else src
                cache[src] = value
                out.write(json.dumps({"s": src, "t": value}, ensure_ascii=False) + "\n")
            out.flush()
            for src in skip:
                cache.setdefault(src, src)
            done[0] += len(batch)
            if done[0] % (args.batch * args.workers) < args.batch:
                print(f"progress {done[0]}/{len(todo)} ({100 * done[0] / max(1, len(todo)):.1f}%)", flush=True)

    started = time.time()
    batches = [todo[i : i + args.batch] for i in range(0, len(todo), args.batch)]
    with futures.ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, batches))

    with lock:
        for src in skip:
            cache.setdefault(src, src)
    json.dump(cache, (args.work / "cache.json").open("w", encoding="utf-8"), ensure_ascii=False)
    translated = sum(1 for k, v in cache.items() if k != v)
    print(f"done: {len(cache)} entries, {translated} translated, {(time.time() - started) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
