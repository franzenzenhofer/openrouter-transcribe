"""Stage 6: one review file per chunk (work/final/NNN.json) plus work/review-report.md.

The review file holds the transcript the reviewer edits: the listener's turns, named by the
voices stage, with every automatic finding attached. An existing review file holds reviewer
edits and is never overwritten.
"""

from typing import Any

from openrouter_transcribe.config import Project, parse_clock
from openrouter_transcribe.findings import Span, compare, conflicts, gaps, numbers_in, snippet
from openrouter_transcribe.plan import Chunk, format_clock, turn_ends
from openrouter_transcribe.review import STATUS_PENDING, joined, report
from openrouter_transcribe.store import (
    load_chunks,
    raw_path,
    read_json,
    stage_path,
    voices_dir,
    write_json,
)


def draft_spans(payload: dict[str, Any]) -> list[Span]:
    return [(float(segment["start"]), float(segment["end"]), str(segment["text"]))
            for segment in payload.get("segments") or []]


def final_turns(project: Project, chunk: Chunk) -> list[dict[str, Any]]:
    listened = read_json(stage_path(project, "listen", chunk))["turns"]
    named = read_json(voices_dir(project) / "assignments" / f"{chunk.name}.json")
    if len(named) != len(listened):
        raise RuntimeError(f"chunk {chunk.name}: voices out of date - rerun `voices`")
    return [{"start": format_clock(row["start_seconds"]), "start_seconds": row["start_seconds"],
             "speaker": row["speaker"], "text": turn["text"], "heard": row["heard"],
             "decided_by": row["decided_by"], "similarity": row["similarity"],
             "margin": row["margin"], "voice_flags": row["flags"]}
            for turn, row in zip(listened, named, strict=True)]


def listener_texts(project: Project, chunk: Chunk) -> dict[str, str]:
    texts = {role: str(read_json(raw_path(project, chunk, project.models[role]))["text"])
             for role in ("whisper", "stt")}
    return {**texts, "second": joined(read_json(stage_path(project, "second", chunk))["turns"])}


def review_block(project: Project, chunk: Chunk, turns: list[dict[str, Any]]) -> dict[str, Any]:
    text = joined(turns)
    others = listener_texts(project, chunk)
    comparison = compare(text, others)
    starts = [float(turn["start_seconds"]) for turn in turns]
    spans = [(start, end, turn["text"])
             for start, end, turn in zip(starts, turn_ends(starts, chunk.seconds), turns,
                                         strict=True)]
    stt = read_json(raw_path(project, chunk, project.models["stt"]))
    reference = draft_spans(stt) or draft_spans(
        read_json(raw_path(project, chunk, project.models["whisper"])))
    second = [(parse_clock(turn["start"]), turn["speaker"])
              for turn in read_json(stage_path(project, "second", chunk))["turns"]]
    named_spans = [(start, end, turn["speaker"], said)
                   for (start, end, said), turn in zip(spans, turns, strict=True)]
    disputed = conflicts(named_spans, second, set(project.names))
    holes = gaps(spans, reference, chunk.seconds)
    flags = [*comparison.flags, *holes]
    if disputed:
        flags.append(f"{len(disputed)} turns where the second listener names someone else")
    voice_flagged = sum(bool(turn["voice_flags"]) for turn in turns)
    if voice_flagged:
        flags.append(f"{voice_flagged} turns with a voice flag")
    return {
        "status": STATUS_PENDING, "reviewer_note": "", "flags": flags,
        "speaker_conflicts": disputed, "words": comparison.words,
        "unsupported_numbers": {number: snippet(text, number)
                                for number in comparison.unsupported},
        "missing_numbers": {number: {name: snippet(other, number)
                                     for name, other in others.items()
                                     if number in numbers_in(other)}
                            for number in comparison.missing},
        "unintelligible": text.count(project.unintelligible),
        "model_notes": read_json(stage_path(project, "listen", chunk))["notes"],
    }


def prepare_chunk(project: Project, chunk: Chunk) -> dict[str, Any]:
    target = stage_path(project, "final", chunk)
    if target.exists():
        existing: dict[str, Any] = read_json(target)
        return existing
    turns = final_turns(project, chunk)
    final = {"chunk": chunk.to_json(), "review": review_block(project, chunk, turns),
             "turns": turns}
    write_json(target, final)
    return final


def run(project: Project) -> None:
    finals = [prepare_chunk(project, chunk) for chunk in load_chunks(project)]
    pending = report(project, finals)
    print(f"{len(finals)} review files, {pending} pending; report at "
          f"{project.work / 'review-report.md'}", flush=True)
