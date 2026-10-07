"""`relisten CHUNK MM:SS`: an ear for one disputed passage.

Cuts a short clip around a moment of a chunk from the original recording and asks a strong
listening model what is said there and by whom, with the review file's turns as context. The
answer is printed and logged in work/relisten.jsonl; nothing is changed.
"""

import json
from pathlib import Path
from typing import Any

from openrouter_transcribe.audio import cut_mp3
from openrouter_transcribe.config import Project, parse_clock
from openrouter_transcribe.openrouter import audio_part, chat_json
from openrouter_transcribe.plan import format_clock
from openrouter_transcribe.prompt import roster_text, turns_text
from openrouter_transcribe.store import ledger_path, load_chunks, read_json, stage_path

RADIUS_SECONDS = 15.0
CONTEXT_SECONDS = 45.0
MAX_OUTPUT_TOKENS = 8000

RELISTEN_PROMPT = """\
You hear a short CLIP from a long recording. Setting:
{setting}

Roster:
{roster}

The CLIP runs from {begin} to {end} of its section. Below is the current transcript of that
stretch. Write verbatim what is said in the CLIP, as turns with speaker names from the roster
("{unclear}" if you cannot tell), each with its MM:SS time in the section. Then say which words
or speakers of the current transcript are wrong. Only what you actually hear; mark what you
cannot understand as "{unintelligible}".
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "turns": {"type": "array", "items": {
            "type": "object",
            "properties": {"at": {"type": "string"}, "speaker": {"type": "string"},
                           "text": {"type": "string"}},
            "required": ["at", "speaker", "text"], "additionalProperties": False}},
        "corrections": {"type": "string"},
    },
    "required": ["turns", "corrections"],
    "additionalProperties": False,
}


def clip_path(project: Project, chunk_name: str, begin: float) -> Path:
    return project.work / "relisten" / f"{chunk_name}-{int(begin):04d}.mp3"


def run_one(project: Project, index: int, moment: str) -> dict[str, Any]:
    chunk = next(chunk for chunk in load_chunks(project) if chunk.index == index)
    centre = parse_clock(moment)
    begin, end = max(0.0, centre - RADIUS_SECONDS), min(chunk.seconds, centre + RADIUS_SECONDS)
    clip = clip_path(project, chunk.name, begin)
    if not clip.exists():
        cut_mp3(project.source(chunk.source).path, chunk.start + begin, chunk.start + end, clip)
    turns = [turn for turn in read_json(stage_path(project, "final", chunk))["turns"]
             if abs(float(turn.get("start_seconds", parse_clock(turn["start"]))) - centre)
             <= CONTEXT_SECONDS]
    prompt = RELISTEN_PROMPT.format(
        setting=project.setting, roster=roster_text(project), begin=format_clock(begin),
        end=format_clock(end), unclear=project.unclear, unintelligible=project.unintelligible)
    body = {
        "model": project.models["second"],
        "messages": [{"role": "system", "content": prompt},
                     {"role": "user", "content": [
                         {"type": "input_audio", "input_audio": audio_part(clip)},
                         {"type": "text", "text": "CURRENT TRANSCRIPT:\n" + turns_text(turns)}]}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "relisten", "strict": True, "schema": SCHEMA}},
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    result = chat_json(body, f"relisten {chunk.name} {moment}", ledger_path(project))
    record = {"chunk": index, "at": moment, "model": project.models["second"], **result}
    with (project.work / "relisten.jsonl").open("a") as log:
        log.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def print_relisten(project: Project, index: int, moment: str) -> None:
    record = run_one(project, index, moment)
    for turn in record["turns"]:
        print(f"[{turn['at']}] {turn['speaker']}: {turn['text']}")
    print(f"\ncorrections: {record['corrections']}")
