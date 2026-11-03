"""Cheap call transcript: one OpenRouter call per mp3 chunk to google/gemini-2.5-flash.

Chunks are stereo: left channel = the recording user, right channel = the remote side (system audio).
Usage: python3 -I transcribe.py --chunks-dir DIR --out transcript.md [--title T] [--language German]
       [--participants "Franz Enzenhofer (left channel); Martin Schipany (right channel)"]
       [--chunk-sec 1080] [--model google/gemini-2.5-flash]
Key: env var OPENROUTER_API_KEY (never stored in the skill).
"""
import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.request

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_UPLOAD_BYTES = 5_000_000
REQUEST_TIMEOUT_S = 600


def build_prompt(args: argparse.Namespace, offset_s: int) -> str:
    start = f"{offset_s // 60:02d}:{offset_s % 60:02d}"
    return (
        f"Transcribe this {args.language} conversation completely and verbatim (no summary, leave nothing out). "
        f"Title: {args.title}. Participants: {args.participants}. "
        "The audio is STEREO: the LEFT channel is the person who made the recording (the first participant), "
        "the RIGHT channel is everyone else on the call (system audio). Use the channel to attribute speakers; "
        "the same remote voice may faintly appear on the left channel as echo - do not duplicate such lines. "
        f"This clip starts at {start} (mm:ss) of the whole call; give timestamps relative to the clip start. "
        "Format: one line per speaker change: [mm:ss] Name: text. Unclear passages as [inaudible]. "
        "Unknown speakers as 'Speaker 3' etc."
    )


def transcribe_chunk(path: pathlib.Path, prompt: str, model: str, key: str) -> dict:
    size = path.stat().st_size
    if size >= MAX_UPLOAD_BYTES:
        sys.exit(f"{path} is {size} bytes, over the {MAX_UPLOAD_BYTES} upload limit - re-cut with a smaller --chunk-sec")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "input_audio", "input_audio": {"data": base64.b64encode(path.read_bytes()).decode(), "format": "mp3"}},
        ]}],
        "max_tokens": 32000,
        "temperature": 0,
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        result = json.load(resp)
    if "choices" not in result:
        sys.exit(f"API error for {path.name}: {json.dumps(result)[:800]}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="Call")
    parser.add_argument("--language", default="German")
    parser.add_argument("--participants", default="unknown")
    parser.add_argument("--chunk-sec", type=int, default=1080)
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    args = parser.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set. Export it first, e.g. export OPENROUTER_API_KEY=$(cat <key file>)")
    chunks = sorted(pathlib.Path(args.chunks_dir).glob("chunk-*.mp3"))
    if not chunks:
        sys.exit(f"no chunk-*.mp3 in {args.chunks_dir}")

    parts = [f"# Transcript {args.title} ({args.model}, automatic)\n"]
    total_cost = 0.0
    for index, chunk in enumerate(chunks):
        offset = index * args.chunk_sec
        result = transcribe_chunk(chunk, build_prompt(args, offset), args.model, key)
        text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        total_cost += float(usage.get("cost", 0) or 0)
        print(f"{chunk.name}: {len(text)} chars, finish={result['choices'][0].get('finish_reason')}, usage={json.dumps(usage)}")
        parts.append(f"\n## Clip {index + 1} (starts at {offset // 60:02d}:{offset % 60:02d})\n\n{text}\n")
    pathlib.Path(args.out).write_text("\n".join(parts), encoding="utf-8")
    print(f"written {args.out}, cost {total_cost:.4f} USD")


if __name__ == "__main__":
    main()
