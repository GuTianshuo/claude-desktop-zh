"""Translation engine: batched, placeholder-safe EN -> zh-Hans over any
OpenAI-compatible /v1/chat/completions endpoint (llama.cpp, Ollama, vLLM,
SiliconFlow, DeepSeek, ...).

Everything goes through a resumeable JSONL cache, so the job can be stopped
and restarted at any time without losing work.
"""
from __future__ import annotations

import json
import os
import re
import time

import urllib.error
import urllib.request

BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("TRANSLATE_MODEL", "local")
BATCH = int(os.environ.get("TRANSLATE_BATCH", "32"))
TIMEOUT = int(os.environ.get("TRANSLATE_TIMEOUT", "600"))

SYSTEM_PROMPT = """You are a professional UI localization engine for a desktop application. \
You translate English UI strings into Simplified Chinese (zh-Hans).
Rules:
1. Output a JSON array with exactly the same number of elements, in the same order.
2. Keep every placeholder exactly as written, e.g. {name}, {count}, {0}, %s.
3. Keep ICU syntax valid: {count, plural, one {…} other {…}} / {x, select, a {…} other {…}} \
— translate only the inner text.
4. Keep HTML tags such as <b>, <keep>, </b> and escape sequences like \\n unchanged.
5. Keep product names in English: Claude, Anthropic, Claude Code, MCP, GitHub, Slack, Chrome.
6. Use concise, natural, professional Chinese wording as used in Chinese software UIs.
7. Never output empty strings; if a string is a bare symbol, product name or file name, copy it unchanged.
Output only the JSON array, no explanation."""

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_ICU = re.compile(r"\{\s*\w+\s*,\s*(plural|select|selectordinal)\b")


def _post(payload: dict, timeout: int = TIMEOUT) -> dict:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _parse_array(content: str) -> list[str]:
    text = re.sub(r"^[\s\S]*?```(?:json)?\s*", "", content)
    text = re.sub(r"\s*```[\s\S]*$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end < start:
        raise ValueError("model returned no JSON array")
    return json.loads(text[start : end + 1])


def _exact(texts: list[str], retries: int) -> list[str]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
    ]
    last: str = ""
    for attempt in range(retries + 1):
        try:
            resp = _post(
                {
                    "model": MODEL,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": 6144,
                    # llama.cpp / vLLM honour this; ignored elsewhere
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
            out = _parse_array(resp["choices"][0]["message"]["content"])
            if len(out) == len(texts):
                return out
            last = f"length {len(out)} != {len(texts)}"
        except Exception as exc:  # noqa: BLE001 - retry any transport/shape error
            last = repr(exc)[:200]
        time.sleep(1 + attempt * 2)
    raise RuntimeError(f"batch failed: {last}")


def translate(texts: list[str], retries: int = 1) -> list[str]:
    """Translate a batch, splitting it in half whenever the model misbehaves."""
    if not texts:
        return []
    try:
        return _exact(texts, retries)
    except Exception:  # noqa: BLE001
        if len(texts) == 1:
            return [texts[0]]
        mid = len(texts) // 2
        return translate(texts[:mid], retries) + translate(texts[mid:], retries)


def placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER.findall(_ICU.sub("", text)))


def looks_translatable(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", text)) and not re.fullmatch(r"[\W\d_]+", text)


def valid(src: str, dst: str) -> bool:
    """Reject output that would break the app (lost placeholders, broken ICU)."""
    if not isinstance(dst, str) or not dst.strip():
        return False
    if "```" in dst:
        return False
    if placeholders(src) != placeholders(dst):
        return False
    if src.count("{") != dst.count("{") or src.count("}") != dst.count("}"):
        return False
    if looks_translatable(src) and not re.search(r"[\u4e00-\u9fff]", dst):
        # allowed only for short brand/acronym strings copied verbatim
        if dst.strip() != src.strip():
            return False
        if len(re.findall(r"[A-Za-z]", src)) > 24:
            return False
    return True
