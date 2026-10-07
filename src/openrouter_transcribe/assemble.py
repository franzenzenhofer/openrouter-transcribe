"""Stage 9: knit the reviewed chunks into <output>.md (to read) and <output>.jsonl (to analyse).

Refuses while any chunk is unreviewed or a turn carries a label outside the roster.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any

from openrouter_transcribe.config import Project, parse_clock
from openrouter_transcribe.plan import Chunk, turn_ends
from openrouter_transcribe.review import STATUS_REVIEWED
from openrouter_transcribe.store import load_chunks, read_json, stage_path

PLAIN_HYPHENS = {0x2013: "-", 0x2014: "-"}  # en and em dash


def clock(chunk: Chunk, seconds: float) -> datetime:
    """Clock time of a moment inside a chunk, interpolated across its wall-clock span."""
    begin = datetime.fromisoformat(chunk.wall_start)
    span = (datetime.fromisoformat(chunk.wall_end) - begin).total_seconds()
    return begin + timedelta(seconds=min(seconds, chunk.seconds) * span / chunk.seconds)


def spoken(project: Project, text: str) -> str:
    for pattern in project.fillers:
        text = re.sub(pattern, "", text)
    return " ".join(text.translate(PLAIN_HYPHENS).split())


def records(project: Project, chunk: Chunk) -> list[dict[str, Any]]:
    final = read_json(stage_path(project, "final", chunk))
    if final["review"]["status"] != STATUS_REVIEWED:
        raise RuntimeError(f"chunk {chunk.name} has not been reviewed yet")
    allowed = {*project.names, project.unclear, project.several}
    turns = final["turns"]
    starts = [float(turn.get("start_seconds", parse_clock(turn["start"]))) for turn in turns]
    rows = []
    for turn, start, end in zip(turns, starts, turn_ends(starts, chunk.seconds), strict=True):
        if turn["speaker"] not in allowed:
            raise KeyError(f"chunk {chunk.name}: label {turn['speaker']!r} is not in the roster")
        text = spoken(project, turn["text"])
        rows.append({"session": chunk.source, "chunk": chunk.index,
                     "start": clock(chunk, start).isoformat(timespec="seconds"),
                     "end": clock(chunk, end).isoformat(timespec="seconds"),
                     "speaker": turn["speaker"], "text": text, "words": len(text.split()),
                     "named_by": turn.get("decided_by", "reviewer"),
                     "voice_similarity": turn.get("similarity")})
    return rows


def speaker_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Words, turns and speaking minutes per label, in order of first appearance."""
    stats: dict[str, dict[str, float]] = {}
    for row in rows:
        entry = stats.setdefault(row["speaker"], {"words": 0, "turns": 0, "minutes": 0.0})
        spoken_for = datetime.fromisoformat(row["end"]) - datetime.fromisoformat(row["start"])
        entry["words"] += row["words"]
        entry["turns"] += 1
        entry["minutes"] += spoken_for.total_seconds() / 60
    return stats


def speaker_meanings(project: Project) -> list[tuple[str, str]]:
    meanings = [(person.name, person.role or person.description) for person in project.people]
    return [*meanings, (project.unclear, "a voice that could not be attributed."),
            (project.several, "several people at once.")]


def speakers_section(project: Project, rows: list[dict[str, Any]]) -> list[str]:
    stats = speaker_stats(rows)
    total = max(1.0, sum(entry["words"] for entry in stats.values()))
    lines = ["## Speakers", "", "| Speaker | Share of words | Minutes | Who |", "|---|---|---|---|"]
    for name, meaning in speaker_meanings(project):
        if name in stats:
            share, minutes = stats[name]["words"] / total, stats[name]["minutes"]
            lines.append(f"| **{name}** | {share:.0%} | {minutes:.0f} | {meaning} |")
    return [*lines, ""]


def merged(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consecutive turns of one speaker as one paragraph (for reading; the JSONL keeps all)."""
    paragraphs: list[dict[str, Any]] = []
    for row in rows:
        if paragraphs and paragraphs[-1]["speaker"] == row["speaker"]:
            paragraphs[-1] = {**paragraphs[-1], "text": f"{paragraphs[-1]['text']} {row['text']}"}
        else:
            paragraphs.append(row)
    return paragraphs


def method_section(project: Project, chunks: list[Chunk]) -> list[str]:
    hours = sum(chunk.seconds for chunk in chunks) / 3600
    models = project.models
    return [
        "## How this transcript was made", "",
        f"- {hours:.1f} hours of audio in {len(chunks)} chunks, cut at quiet moments from "
        f"{len(project.sources)} checksum-verified recordings that were only ever read.",
        f"- Drafts: `{models['whisper']}` and `{models['stt']}`. `{models['listener']}` heard "
        f"each chunk with both drafts and wrote the turns; `{models['second']}` listened "
        "independently as a cross-check.",
        "- Speaker names: local voice fingerprints (sherpa-onnx, "
        f"{', '.join(project.voices.models)}) enrolled from each person's own introduction, "
        "checked against who the listening model heard; disagreements were reviewed.",
        f"- `{models['auditor']}` heard every chunk again against the transcript and listed "
        "omissions, misheard words and wrong speakers; a reviewer applied them chunk by chunk.",
        f"- `{project.unintelligible}` marks speech that could not be understood.", "",
    ]


def run(project: Project) -> None:
    chunks = load_chunks(project)
    by_chunk = {chunk.index: records(project, chunk) for chunk in chunks}
    rows = [row for chunk in chunks for row in by_chunk[chunk.index]]
    lines = [f"# {project.title}", "", *method_section(project, chunks),
             *speakers_section(project, rows)]
    for source in project.sources:
        lines += [f"## {source.title} ({source.wall_start:%H:%M} - {source.wall_end:%H:%M})", ""]
        lines += [f"*{source.note}*", ""] if source.note else []
        for chunk in (chunk for chunk in chunks if chunk.source == source.key):
            lines += [f"### {chunk.wall_start[11:16]} - {chunk.wall_end[11:16]}", ""]
            for row in merged(by_chunk[chunk.index]):
                lines += [f"**{row['speaker']}** [{row['start'][11:19]}]: {row['text']}", ""]
    markdown = project.root / f"{project.output}.md"
    markdown.write_text("\n".join(lines))
    (project.root / f"{project.output}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    document = transcript_document(project, chunks, rows)
    (project.root / f"{project.output}.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=1))
    print(f"wrote {project.output}.md, .json and .jsonl: {len(rows)} turns, "
          f"{sum(row['words'] for row in rows)} words", flush=True)


def transcript_document(project: Project, chunks: list[Chunk],
                        rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The whole transcript as one JSON document: metadata, speakers with stats, all turns."""
    stats = speaker_stats(rows)
    total = max(1.0, sum(entry["words"] for entry in stats.values()))
    return {
        "title": project.title, "language": project.language,
        "hours": round(sum(chunk.seconds for chunk in chunks) / 3600, 2),
        "sessions": [{"key": source.key, "title": source.title,
                      "start": source.wall_start.isoformat(), "end": source.wall_end.isoformat(),
                      "note": source.note} for source in project.sources],
        "models": project.models, "voice_models": list(project.voices.models),
        "speakers": [{"name": name, "who": meaning, "words": int(stats[name]["words"]),
                      "share_of_words": round(stats[name]["words"] / total, 4),
                      "turns": int(stats[name]["turns"]),
                      "minutes": round(stats[name]["minutes"], 1)}
                     for name, meaning in speaker_meanings(project) if name in stats],
        "turns": [{"id": index + 1, **row} for index, row in enumerate(rows)],
    }
