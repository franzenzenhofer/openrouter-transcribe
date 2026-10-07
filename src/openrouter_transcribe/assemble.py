"""Stage 9: knit the reviewed chunks into <output>.md (to read) and <output>.jsonl (to analyse).

Refuses while any chunk is unreviewed or a turn carries a label outside the roster.
"""

import json
import re
from collections import Counter
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


def speakers_section(project: Project, rows: list[dict[str, Any]]) -> list[str]:
    words = Counter[str]()
    for row in rows:
        words[row["speaker"]] += row["words"]
    total = max(1, sum(words.values()))
    lines = ["## Speakers", ""]
    for person in project.people:
        if words[person.name]:
            lines.append(f"- **{person.name}** ({words[person.name] / total:.0%} of words): "
                         f"{person.description}")
    lines += [f"- **{label}** ({words[label] / total:.0%} of words): {meaning}"
              for label, meaning in ((project.unclear, "a voice that could not be attributed."),
                                     (project.several, "several people at once."))
              if words[label]]
    return [*lines, ""]


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
            for row in by_chunk[chunk.index]:
                lines += [f"**{row['speaker']}** [{row['start'][11:19]}]: {row['text']}", ""]
    markdown = project.root / f"{project.output}.md"
    markdown.write_text("\n".join(lines))
    (project.root / f"{project.output}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(f"wrote {markdown.name} and {project.output}.jsonl: {len(rows)} turns, "
          f"{sum(row['words'] for row in rows)} words", flush=True)
