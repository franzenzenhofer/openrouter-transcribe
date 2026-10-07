"""Review bookkeeping: the status report, sign-off, and side-by-side passages for a reviewer."""

import re
from typing import Any

from openrouter_transcribe.config import Project
from openrouter_transcribe.store import load_chunks, raw_path, read_json, stage_path, write_json

STATUS_PENDING = "pending"
STATUS_REVIEWED = "reviewed"
PASSAGE_RADIUS = 220


def joined(turns: list[dict[str, Any]]) -> str:
    return "\n".join(str(turn["text"]) for turn in turns)


def report_row(final: dict[str, Any]) -> str:
    chunk, review = final["chunk"], final["review"]
    speakers = sorted({turn["speaker"] for turn in final["turns"]})
    audit = review.get("audit")
    audited = "-" if audit is None else str(len(audit["findings"]))
    return (f"| {chunk['index']:03d} | {chunk['wall_start'][11:16]} | {review['status']} | "
            f"{review['words']['final']} | {review['unintelligible']} | {audited} | "
            f"{', '.join(speakers)} | {'; '.join(review['flags']) or '-'} |")


def report(project: Project, finals: list[dict[str, Any]]) -> int:
    """Writes work/review-report.md; returns the number of chunks still pending."""
    header = ["# Review status per chunk", "",
              "| Chunk | Clock | Status | Words | Unintelligible | Audit findings | Speakers "
              "| Flags |", "|---|---|---|---|---|---|---|---|"]
    rows = [report_row(final) for final in finals]
    (project.work / "review-report.md").write_text("\n".join(header + rows) + "\n")
    return sum(final["review"]["status"] != STATUS_REVIEWED for final in finals)


def finals_of(project: Project) -> list[dict[str, Any]]:
    return [read_json(stage_path(project, "final", chunk)) for chunk in load_chunks(project)]


def approve(project: Project, indices: list[int], note: str) -> None:
    """The reviewer has read these chunks (and edited them where needed)."""
    by_index = {chunk.index: chunk for chunk in load_chunks(project)}
    for index in indices:
        target = stage_path(project, "final", by_index[index])
        final = read_json(target)
        if "audit" not in final["review"]:
            raise RuntimeError(f"chunk {index:03d} has no audit yet - run `audit` first")
        final["review"]["status"] = STATUS_REVIEWED
        final["review"]["reviewer_note"] = note
        write_json(target, final)
    pending = report(project, finals_of(project))
    print(f"marked reviewed: {indices}; {pending} chunks pending")


def print_status(project: Project) -> None:
    pending = report(project, finals_of(project))
    print((project.work / "review-report.md").read_text())
    print(f"{pending} chunks pending")


def listener_texts(project: Project, index: int) -> dict[str, str]:
    chunk = next(chunk for chunk in load_chunks(project) if chunk.index == index)
    texts = {"final": joined(read_json(stage_path(project, "final", chunk))["turns"]),
             "second": joined(read_json(stage_path(project, "second", chunk))["turns"])}
    for role in ("whisper", "stt"):
        texts[role] = str(read_json(raw_path(project, chunk, project.models[role]))["text"])
    return texts


def print_passages(project: Project, index: int, phrase: str) -> None:
    """How every listener rendered the passage around a phrase."""
    for name, text in listener_texts(project, index).items():
        flat = " ".join(text.split())
        matches = list(re.finditer(re.escape(phrase), flat, re.IGNORECASE))
        for match in matches:
            start = max(0, match.start() - PASSAGE_RADIUS)
            print(f"[{name}] ...{flat[start:match.end() + PASSAGE_RADIUS]}...\n")
        if not matches:
            print(f"[{name}] (phrase not found)\n")
