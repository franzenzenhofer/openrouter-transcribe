"""work/voices/report.md: how well the voices separate, and where voice and listener disagree."""

from collections import Counter
from typing import Any

from openrouter_transcribe.config import Project
from openrouter_transcribe.consistency import check
from openrouter_transcribe.speakers import Vector
from openrouter_transcribe.store import voices_dir

EXAMPLES = 40
PREVIEW = 90


def similarity_table(centroids: dict[str, Vector]) -> list[str]:
    names = list(centroids)
    lines = ["| | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for row in names:
        cells = [f"{float(centroids[row] @ centroids[column]):.2f}" for column in names]
        lines.append(f"| **{row}** | " + " | ".join(cells) + " |")
    return lines


def agreement(rows: list[dict[str, Any]], basis: str | None, people: set[str]) -> str:
    chosen = [row for row in rows if row["heard"] in people and row["decided_by"] != "none"
              and (basis is None or row["basis"] == basis)
              and row["end_seconds"] - row["start_seconds"] >= 2.5]
    same = sum(row["heard"] == row["voice_best"] for row in chosen)
    return f"{same} of {len(chosen)} ({same / len(chosen):.0%})" if chosen else "no turns"


def speaker_table(rows: list[dict[str, Any]]) -> list[str]:
    seconds: Counter[str] = Counter()
    count: Counter[str] = Counter()
    for row in rows:
        seconds[row["speaker"]] += row["end_seconds"] - row["start_seconds"]
        count[row["speaker"]] += 1
    total = sum(seconds.values())
    lines = ["| Speaker | Turns | Minutes | Share of time |", "|---|---|---|---|"]
    lines += [f"| {name} | {count[name]} | {seconds[name] / 60:.1f} | {seconds[name] / total:.0%} |"
              for name, _ in seconds.most_common()]
    return lines


def disagreements(assignments: dict[str, list[dict[str, Any]]],
                  texts: dict[str, list[str]]) -> list[str]:
    lines = ["| Chunk | At | Final | Listener heard | Basis | Similarity | Margin | Text |",
             "|---|---|---|---|---|---|---|---|"]
    found = [(name, index, row) for name, rows in assignments.items()
             for index, row in enumerate(rows) if row["speaker"] != row["heard"] or row["flags"]]
    for name, index, row in found[:EXAMPLES]:
        text = texts[name][index][:PREVIEW].replace("|", "/")
        cells = [name, f"{row['start_seconds']:.0f}s", row["speaker"], row["heard"], row["basis"],
                 str(row["similarity"]), str(row["margin"]), text]
        lines.append("| " + " | ".join(cells) + " |")
    return [f"{len(found)} turns where the final name differs from the listener or carries a "
            f"flag (first {EXAMPLES}):", "", *lines]


def write_report(project: Project, centroids: dict[str, Vector],
                 assignments: dict[str, list[dict[str, Any]]],
                 texts: dict[str, list[str]]) -> None:
    """`texts` holds the turn texts per chunk, in the same order as `assignments`."""
    rows = [row for chunk_rows in assignments.values() for row in chunk_rows]
    people = set(centroids)
    decided = Counter(row["decided_by"] for row in rows)
    lines = [
        "# Voice naming report", "",
        f"Embedding models: {', '.join(project.voices.models)}. Thresholds: similarity >= "
        f"{project.voices.min_similarity}, margin >= {project.voices.min_margin}.", "",
        "## Enrolled voices (cosine similarity between centroids; lower = better separated)", "",
        *similarity_table(centroids), "",
        "## Who speaks", "", *speaker_table(rows), "",
        "## How each turn was decided", "",
        *[f"- {key}: {value}" for key, value in decided.most_common()], "",
        "## Voice vs listener (turns of 2.5 s and more)", "",
        f"- all turns with a roster name: {agreement(rows, None, people)}",
        f"- turns the listener marked `named` (addressed or self-identified): "
        f"{agreement(rows, 'named', people)}", "",
        "## Disagreements and flags", "", *disagreements(assignments, texts), "",
    ]
    (voices_dir(project) / "report.md").write_text("\n".join(lines))


CONSISTENCY_MIN_SECONDS = 4.0
CONSISTENCY_MIN_WORDS = 12


def consistency_lines(title: str, samples: list[tuple[str, Vector]]) -> list[str]:
    result = check([vector for _, vector in samples], [name for name, _ in samples])
    lines = [f"### {title}", "", f"{len(samples)} turns, agreement {result.agreement:.1%}", ""]
    lines += [f"- cluster {index + 1}: " + ", ".join(f"{name} {count}" for name, count in
                                                    sorted(cluster.items(), key=lambda x: -x[1]))
              for index, cluster in enumerate(result.clusters)]
    return [*lines, ""]


def append_consistency(project: Project, turns: list[tuple[dict[str, Any], str, Vector]]) -> None:
    """Clusters the long turns (row, text, vector) without names, with and without the main
    speaker, and appends how far the clusters coincide with the final names."""
    people = set(project.names)
    long_turns = [(row["speaker"], vector) for row, text, vector in turns
                  if row["speaker"] in people
                  and row["end_seconds"] - row["start_seconds"] >= CONSISTENCY_MIN_SECONDS
                  and len(text.split()) >= CONSISTENCY_MIN_WORDS]
    main = Counter(name for name, _ in long_turns).most_common(1)[0][0] if long_turns else ""
    lines = ["## Independent check: clusters without names", "",
             "Long turns clustered by voice alone (k = number of people). Agreement = share of "
             "turns whose cluster majority is their own name. Below 90% means people are mixed up.",
             "", *consistency_lines("Everyone", long_turns),
             *consistency_lines(f"Everyone except {main}",
                                [item for item in long_turns if item[0] != main])]
    with (voices_dir(project) / "report.md").open("a") as report:
        report.write("\n".join(lines))
