"""Stage 3: a listening model hears each chunk with both drafts and writes speaker turns.

Chunks are independent (fixed roster from the project file), so they run in parallel. Names
come from context here; the voices stage checks them against the actual voices.
"""

import unicodedata
from pathlib import Path
from typing import Any

from openrouter_transcribe.config import Project, parse_clock
from openrouter_transcribe.openrouter import audio_part, chat_json
from openrouter_transcribe.plan import Chunk, format_clock
from openrouter_transcribe.prompt import LISTEN_SCHEMA, system_prompt, timed_draft
from openrouter_transcribe.runner import run_all
from openrouter_transcribe.store import (
    chunk_audio,
    ledger_path,
    load_chunks,
    raw_path,
    read_json,
    stage_path,
    write_json,
)

MAX_OUTPUT_TOKENS = 40000
ATTEMPTS = 3
TIMESTAMP_SLACK_SECONDS = 10.0


def task_text(project: Project, chunk: Chunk) -> str:
    drafts = [f"Draft by {project.models[role]}:\n"
              + timed_draft(read_json(raw_path(project, chunk, project.models[role])))
              for role in ("whisper", "stt")]
    return "\n\n".join([f"AUDIO is {format_clock(chunk.seconds)} long and starts at clock time "
                        f"{chunk.wall_start[11:19]}.", *drafts,
                        "Now transcribe AUDIO completely, following the rules."])


def folded(label: str) -> str:
    """"Zoë", "zoe " and "ZOE" compare equal."""
    plain = unicodedata.normalize("NFKD", label.strip()).encode("ascii", "ignore").decode()
    return plain.casefold()


def canonical_speakers(project: Project, turns: list[dict[str, str]]) -> None:
    """Map spelling variants of roster labels onto the roster spelling, in place."""
    known = {folded(label): label for label in (*project.names, project.unclear, project.several)}
    for turn in turns:
        turn["speaker"] = known.get(folded(turn["speaker"]), turn["speaker"])


def validate(project: Project, result: dict[str, Any], chunk: Chunk) -> None:
    turns = result["turns"]
    canonical_speakers(project, turns)
    if not turns:
        raise ValueError("no turns")
    starts = [parse_clock(turn["start"]) for turn in turns]
    if starts != sorted(starts):
        raise ValueError("turn start times are not in order")
    if starts[-1] > chunk.seconds + TIMESTAMP_SLACK_SECONDS:
        raise ValueError(f"turn at {starts[-1]:.0f}s is beyond the {chunk.seconds:.0f}s chunk")
    allowed = {*project.names, project.unclear, project.several}
    unknown = {turn["speaker"] for turn in turns} - allowed
    if unknown:
        raise ValueError(f"speaker labels outside the roster: {sorted(unknown)}")
    if any(not turn["text"].strip() for turn in turns):
        raise ValueError("turn with empty text")


def request(project: Project, chunk: Chunk, model: str) -> dict[str, Any]:
    content = [{"type": "input_audio", "input_audio": audio_part(chunk_audio(project, chunk))},
               {"type": "text", "text": task_text(project, chunk)}]
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt(project)},
                     {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "transcript_section", "strict": True, "schema": LISTEN_SCHEMA}},
        "reasoning": {"effort": "low"},
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    result = chat_json(body, f"listen {chunk.name} {model}", ledger_path(project))
    validate(project, result, chunk)
    return {"chunk": chunk.to_json(), "model": model, **result}


def listen_chunk(project: Project, chunk: Chunk, model: str, target: Path) -> str:
    """An invalid answer is asked for again; after ATTEMPTS the chunk fails loudly."""
    if target.exists():
        return f"{chunk.name}: cached"
    problems: list[str] = []
    for _ in range(ATTEMPTS):
        try:
            result = request(project, chunk, model)
        except (ValueError, KeyError) as problem:
            problems.append(str(problem))
            continue
        write_json(target, result)
        return f"{chunk.name}: {len(result['turns'])} turns ({model})"
    raise RuntimeError(f"chunk {chunk.name}: no valid answer from {model}: {problems}")


def run_with(project: Project, role: str, stage: str) -> None:
    model = project.models[role]
    chunks = load_chunks(project)
    run_all(chunks, lambda chunk: listen_chunk(project, chunk, model,
                                               stage_path(project, stage, chunk)),
            project.workers, stage)


def run(project: Project) -> None:
    run_with(project, "listener", "listen")
