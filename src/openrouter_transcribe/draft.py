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


def draft_chunk(project: Project, chunk: Chunk, model: str) -> str:
    target = raw_path(project, chunk, model)
    if target.exists():
        return f"{chunk.name} {model}: cached"
    body = {"model": model, "input_audio": audio_part(chunk_audio(project, chunk)),
            "language": project.language, "response_format": "verbose_json"}
    payload = post(TRANSCRIPTION_ENDPOINT, body, f"draft {chunk.name}", ledger_path(project))
    if not str(payload.get("text", "")).strip():
        raise RuntimeError(f"chunk {chunk.name}: {model} returned no text")
    write_json(target, payload)
    return f"{chunk.name} {model}: {len(str(payload['text']).split())} words"


def run(project: Project) -> None:
    models = [project.models[role] for role in DRAFT_ROLES]
    jobs = [(chunk, model) for chunk in load_chunks(project) for model in models]
    run_all(jobs, lambda job: draft_chunk(project, *job), project.workers, "draft")
