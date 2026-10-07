"""Stage 7: a model hears each chunk again next to its review file and lists what is wrong.

This is the ear for the reviewer, who works without audio: omissions (said but not written),
misheard words, wrong speakers, invented text, two speakers merged into one turn. The audit
never changes turns; it is stored in the review file under review.audit.
"""

from typing import Any

from openrouter_transcribe.config import Project
from openrouter_transcribe.openrouter import audio_part, chat_json
from openrouter_transcribe.plan import Chunk
from openrouter_transcribe.prompt import roster_text, turns_text
from openrouter_transcribe.runner import run_all
from openrouter_transcribe.store import (
    chunk_audio,
    ledger_path,
    load_chunks,
    read_json,
    stage_path,
    write_json,
)

KINDS = ("omission", "misheard", "wrong_speaker", "invented", "merged_turns")
MAX_OUTPUT_TOKENS = 20000
ATTEMPTS = 3

AUDIT_PROMPT = """\
You audit a verbatim transcript of one section of a long recording against the AUDIO.
Setting:
{setting}

Roster:
{roster}

Report every place where the transcript is wrong, as findings:
- omission: something audibly said that the transcript does not contain. Give the exact words
  in "heard" and who said them in "speaker". Be exhaustive: short answers, side remarks and
  small talk count.
- misheard: the transcript has different words than were said (names, numbers, terms).
- wrong_speaker: the turn is attributed to the wrong person; give the right one in "speaker".
- invented: the transcript contains words nobody said.
- merged_turns: one turn contains speech of two people; "heard" says where the second starts.
Ignore filled pauses, stutters, punctuation and harmless spelling. Do not restyle. "at" is the
MM:SS in AUDIO. If the transcript is correct, return no findings.
"""

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "at": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)},
        "transcript": {"type": "string"}, "heard": {"type": "string"},
        "speaker": {"type": "string"},
    },
    "required": ["at", "kind", "transcript", "heard", "speaker"],
    "additionalProperties": False,
}
AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": FINDING_SCHEMA},
                   "summary": {"type": "string"}},
    "required": ["findings", "summary"],
    "additionalProperties": False,
}


def request(project: Project, chunk: Chunk, final: dict[str, Any]) -> dict[str, Any]:
    model = project.models["auditor"]
    content = [{"type": "input_audio", "input_audio": audio_part(chunk_audio(project, chunk))},
               {"type": "text", "text": "TRANSCRIPT:\n" + turns_text(final["turns"])}]
    body = {
        "model": model,
        "messages": [{"role": "system", "content": AUDIT_PROMPT.format(
            setting=project.setting, roster=roster_text(project))},
                     {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "audit", "strict": True, "schema": AUDIT_SCHEMA}},
        "reasoning": {"effort": "medium"},
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    result = chat_json(body, f"audit {chunk.name}", ledger_path(project))
    return {"model": model, **result}


def audit_chunk(project: Project, chunk: Chunk) -> str:
    target = stage_path(project, "final", chunk)
    final = read_json(target)
    if "audit" in final["review"]:
        return f"{chunk.name}: cached"
    problems: list[str] = []
    for _ in range(ATTEMPTS):
        try:
            audit = request(project, chunk, final)
        except (ValueError, KeyError) as problem:
            problems.append(str(problem))
            continue
        write_json(stage_path(project, "audit", chunk), audit)
        final = read_json(target)
        final["review"]["audit"] = audit
        write_json(target, final)
        return f"{chunk.name}: {len(audit['findings'])} findings"
    raise RuntimeError(f"chunk {chunk.name}: no valid audit: {problems}")


def run(project: Project) -> None:
    run_all(load_chunks(project), lambda chunk: audit_chunk(project, chunk), project.workers,
            "audit")
