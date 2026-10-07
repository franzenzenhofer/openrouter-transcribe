"""Stage 5: name every turn by its voice. Embeddings are local; nothing is sent anywhere.

Per chunk: decode the original audio, pin each turn's start to the word timing of the drafts,
embed each turn and short analysis windows. Then enrol the people from their samples, re-estimate
from agreeing turns, decide every turn and write work/voices/assignments/NNN.json + report.md.
"""

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from openrouter_transcribe.align import draft_words, refined_starts
from openrouter_transcribe.audio import read_pcm
from openrouter_transcribe.config import Project, parse_clock
from openrouter_transcribe.embed import RATE, Embedder, windows
from openrouter_transcribe.plan import Chunk, turn_ends
from openrouter_transcribe.speakers import Turn, Vector, change_points, decide, enrol
from openrouter_transcribe.store import (
    load_chunks,
    raw_path,
    read_json,
    stage_path,
    voices_dir,
    write_json,
)
from openrouter_transcribe.voice_report import append_consistency, write_report


def cache_path(project: Project, chunk: Chunk) -> Path:
    return voices_dir(project) / "embeddings" / f"{chunk.name}.npz"


def turn_spans(project: Project, chunk: Chunk) -> tuple[list[dict[str, Any]], list[float]]:
    """The listener's turns and their starts, pinned to word timing where a draft has it."""
    turns: list[dict[str, Any]] = read_json(stage_path(project, "listen", chunk))["turns"]
    words = draft_words(read_json(raw_path(project, chunk, project.models["stt"])))
    approx = [min(parse_clock(turn["start"]), chunk.seconds) for turn in turns]
    return turns, refined_starts([turn["text"] for turn in turns], approx, words)


def embed_chunk(project: Project, chunk: Chunk, embedder: Embedder) -> dict[str, Any]:
    """Turn vectors and window vectors for one chunk, cached on disk."""
    target = cache_path(project, chunk)
    turns, starts = turn_spans(project, chunk)
    if target.exists():
        cached = dict(np.load(target))
        if len(cached["starts"]) == len(turns):
            return cached
    audio = read_pcm(project.source(chunk.source).path, chunk.start, chunk.seconds, RATE)
    ends = turn_ends(starts, chunk.seconds)
    turn_vectors = [embedder.embed(audio[int(start * RATE):max(int(end * RATE),
                                                               int(start * RATE) + 1)])
                    for start, end in zip(starts, ends, strict=True)]
    found = windows(audio, project.voices)
    window_vectors = [embedder.embed(piece) for _, piece in found]
    payload: dict[str, NDArray[Any]] = {
        "starts": np.asarray(starts), "ends": np.asarray(ends), "turns": np.stack(turn_vectors),
        "window_times": np.asarray([time for time, _ in found]),
        "windows": np.stack(window_vectors) if window_vectors else np.zeros((0, 1)),
    }
    partial = target.with_suffix(".partial.npz")
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez(partial, starts=payload["starts"], ends=payload["ends"], turns=payload["turns"],
             window_times=payload["window_times"], windows=payload["windows"])
    partial.replace(target)
    return payload


def anchors(project: Project, embedder: Embedder) -> dict[str, list[Vector]]:
    return {person.name: [embedder.embed(read_pcm(project.source(sample.source).path,
                                                  sample.start, sample.end - sample.start, RATE))
                          for sample in person.samples]
            for person in project.people}


def chunk_turns(project: Project, chunk: Chunk, payload: dict[str, Any]) -> list[Turn]:
    listened = read_json(stage_path(project, "listen", chunk))["turns"]
    return [Turn(key=f"{chunk.name}:{index}", heard=turn["speaker"], basis=turn["basis"],
                 seconds=float(end - start), vector=vector)
            for index, (turn, start, end, vector) in enumerate(zip(
                listened, payload["starts"], payload["ends"], payload["turns"], strict=True))]


def assign_chunk(project: Project, chunk: Chunk, payload: dict[str, Any], turns: list[Turn],
                 centroids: dict[str, Vector]) -> list[dict[str, Any]]:
    labels = (project.unclear, project.several)
    times = payload["window_times"]
    rows = []
    for turn, start, end in zip(turns, payload["starts"], payload["ends"], strict=True):
        verdict = decide(turn, centroids, project.voices, labels)
        inside = [index for index, time in enumerate(times)
                  if start <= time and time + project.voices.window_seconds <= end]
        changes = change_points([float(times[i]) for i in inside],
                                [payload["windows"][i] for i in inside],
                                verdict.speaker, centroids, project.voices)
        flags = [*verdict.flags, *(f"possible speaker change at {at:.0f}s ({name})"
                                   for at, name in changes)]
        rows.append({"start_seconds": round(float(start), 2), "end_seconds": round(float(end), 2),
                     "speaker": verdict.speaker, "heard": turn.heard, "basis": turn.basis,
                     "decided_by": verdict.decided_by, "voice_best": verdict.best,
                     "similarity": verdict.similarity, "margin": verdict.margin, "flags": flags})
    return rows


def run(project: Project) -> None:
    embedder = Embedder(project.voices)
    chunks = load_chunks(project)
    payloads = {}
    for chunk in chunks:
        payloads[chunk.name] = embed_chunk(project, chunk, embedder)
        print(f"{chunk.name}: {len(payloads[chunk.name]['starts'])} turns embedded", flush=True)
    turns = {chunk.name: chunk_turns(project, chunk, payloads[chunk.name]) for chunk in chunks}
    centroids = enrol(anchors(project, embedder), [t for ts in turns.values() for t in ts],
                      project.voices.rounds)
    assignments = {}
    for chunk in chunks:
        rows = assign_chunk(project, chunk, payloads[chunk.name], turns[chunk.name], centroids)
        assignments[chunk.name] = rows
        write_json(voices_dir(project) / "assignments" / f"{chunk.name}.json", rows)
    texts = {chunk.name: [turn["text"] for turn in
                          read_json(stage_path(project, "listen", chunk))["turns"]]
             for chunk in chunks}
    write_report(project, centroids, assignments, texts)
    append_consistency(project, [(row, text, turn.vector) for chunk in chunks
                                 for row, text, turn in zip(assignments[chunk.name],
                                                            texts[chunk.name], turns[chunk.name],
                                                            strict=True)])
    print(f"voices: {len(centroids)} people enrolled; report at "
          f"{voices_dir(project) / 'report.md'}", flush=True)
