"""Stage 2: two raw machine drafts per chunk from dedicated speech-to-text models."""

from openrouter_transcribe.config import Project
from openrouter_transcribe.openrouter import TRANSCRIPTION_ENDPOINT, audio_part, post
from openrouter_transcribe.plan import Chunk
from openrouter_transcribe.runner import run_all
from openrouter_transcribe.store import (
    chunk_audio,
    ledger_path,
    load_chunks,
    raw_path,
    write_json,
)

DRAFT_ROLES = ("whisper", "stt")


def draft_summary(chunk_name: str, model: str, payload: dict[str, object]) -> str:
    """The log line for one stored draft. An empty draft is a result, not a failure: on quiet
    stretches (people working, the speaker away from the microphone) one model often returns
    nothing while the other hears words; the listener decides from the audio itself."""
    if "text" not in payload:
        raise RuntimeError(f"chunk {chunk_name}: {model} answered without a text field")
    words = len(str(payload["text"]).split())
    note = " (empty draft, quiet audio)" if words == 0 else ""
    return f"{chunk_name} {model}: {words} words{note}"


def draft_chunk(project: Project, chunk: Chunk, model: str) -> str:
    target = raw_path(project, chunk, model)
    if target.exists():
        return f"{chunk.name} {model}: cached"
    body = {"model": model, "input_audio": audio_part(chunk_audio(project, chunk)),
            "language": project.language, "response_format": "verbose_json"}
    payload = post(TRANSCRIPTION_ENDPOINT, body, f"draft {chunk.name}", ledger_path(project))
    summary = draft_summary(chunk.name, model, payload)
    write_json(target, payload)
    return summary


def run(project: Project) -> None:
    models = [project.models[role] for role in DRAFT_ROLES]
    jobs = [(chunk, model) for chunk in load_chunks(project) for model in models]
    run_all(jobs, lambda job: draft_chunk(project, *job), project.workers, "draft")
