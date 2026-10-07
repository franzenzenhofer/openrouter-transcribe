"""The harness's own state under <project>/work/. Every write is atomic, so every stage resumes."""

import json
from pathlib import Path
from typing import Any

from openrouter_transcribe.config import Project
from openrouter_transcribe.plan import Chunk


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    partial.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def manifest_path(project: Project) -> Path:
    return project.work / "manifest.json"


def load_chunks(project: Project) -> list[Chunk]:
    path = manifest_path(project)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run `prepare` first")
    return [Chunk(**entry) for entry in read_json(path)["chunks"]]


def chunk_audio(project: Project, chunk: Chunk) -> Path:
    return project.work / "chunks" / f"{chunk.name}.mp3"


def raw_path(project: Project, chunk: Chunk, model: str) -> Path:
    return project.work / "raw" / model.replace("/", "_") / f"{chunk.name}.json"


def stage_path(project: Project, stage: str, chunk: Chunk) -> Path:
    """listen/, second/, final/, audit/ - one JSON per chunk."""
    return project.work / stage / f"{chunk.name}.json"


def voices_dir(project: Project) -> Path:
    return project.work / "voices"


def ledger_path(project: Project) -> Path:
    return project.work / "ledger.jsonl"
