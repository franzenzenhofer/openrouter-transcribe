"""Minimal OpenRouter client: retries on transient errors only, and a cost ledger."""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = "https://openrouter.ai/api/v1"
TRANSCRIPTION_ENDPOINT = "/audio/transcriptions"
CHAT_ENDPOINT = "/chat/completions"
REQUEST_TIMEOUT_SECONDS = 600
MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 5
TRANSIENT_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 529})

_ledger_lock = threading.Lock()


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return key


def audio_part(path: Path) -> dict[str, str]:
    """Base64 payload in the shape both endpoints expect for input audio."""
    return {"data": base64.b64encode(path.read_bytes()).decode(), "format": "mp3"}


def _record(ledger: Path, label: str, model: str, usage: object) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label,
                        "model": model, "usage": usage})
    with _ledger_lock, ledger.open("a") as handle:
        handle.write(entry + "\n")


def _send(endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        API_ROOT + endpoint, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload: dict[str, Any] = json.loads(response.read())
    if "error" in payload:
        raise RuntimeError(f"OpenRouter error for {body['model']}: {payload['error']}")
    return payload


def post(endpoint: str, body: dict[str, Any], label: str, ledger: Path) -> dict[str, Any]:
    """POST with retries on transient failures; everything else raises."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            payload = _send(endpoint, body)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:800]
            if error.code not in TRANSIENT_STATUS or attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"{label}: HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"{label}: network failure: {error}") from error
        else:
            _record(ledger, label, str(body["model"]), payload.get("usage"))
            return payload
        time.sleep(RETRY_BASE_SECONDS * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def chat_json(body: dict[str, Any], label: str, ledger: Path) -> dict[str, Any]:
    """A chat call whose answer must be complete JSON."""
    payload = post(CHAT_ENDPOINT, body, label, ledger)
    choice = payload["choices"][0]
    if choice["finish_reason"] != "stop":
        raise ValueError(f"{label}: finish_reason {choice['finish_reason']}")
    result: dict[str, Any] = json.loads(choice["message"]["content"])
    return result


def ledger_cost(ledger: Path) -> dict[str, float]:
    """Billed cost per model according to the ledger."""
    costs: dict[str, float] = {}
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            entry = json.loads(line)
            cost = float((entry.get("usage") or {}).get("cost") or 0.0)
            costs[entry["model"]] = costs.get(entry["model"], 0.0) + cost
    return costs
