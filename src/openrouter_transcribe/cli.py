"""Command line: one subcommand per stage, plus `all` for the automatic stages in order."""

import argparse
import importlib
from pathlib import Path

from openrouter_transcribe.config import Project, load
from openrouter_transcribe.openrouter import ledger_cost
from openrouter_transcribe.store import ledger_path

AUTOMATIC_STAGES = ("prepare", "draft", "listen", "second", "voices", "check", "audit")
STAGE_HELP = {
    "prepare": "1. verify the originals (sha256) and cut chunks at quiet moments",
    "draft": "2. raw drafts from two speech-to-text models",
    "listen": "3. listening model writes the turns from audio + drafts",
    "second": "4. a second, different listening model (cross-check only)",
    "voices": "5. local voice fingerprints name every turn",
    "check": "6. review files per chunk: coverage, numbers, speaker conflicts",
    "audit": "7. a model hears each chunk against its review file: omissions, wrong speakers",
    "assemble": "9. Markdown + JSONL transcript; refuses while a chunk is unreviewed",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openrouter-transcribe", description=__doc__)
    parser.add_argument("-c", "--config", type=Path, default=Path("transcript.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    for stage, text in STAGE_HELP.items():
        commands.add_parser(stage, help=text)
    commands.add_parser("all", help="run stages 1-7 in order (each one resumes)")
    approving = commands.add_parser("approve", help="8. sign off reviewed chunks")
    approving.add_argument("chunks", type=int, nargs="+")
    approving.add_argument("--note", required=True, help="what the reviewer changed, or 'none'")
    passage = commands.add_parser("passage", help="how every listener heard a phrase")
    passage.add_argument("chunk", type=int)
    passage.add_argument("phrase")
    relisten = commands.add_parser("relisten", help="a strong model hears 30 s around a moment")
    relisten.add_argument("chunk", type=int)
    relisten.add_argument("moment", help="MM:SS in the chunk")
    commands.add_parser("status", help="review status of every chunk")
    commands.add_parser("cost", help="billed so far, per model")
    return parser


def run_stage(stage: str, project: Project) -> None:
    importlib.import_module(f"openrouter_transcribe.{stage}").run(project)


def main() -> None:
    arguments = build_parser().parse_args()
    project = load(arguments.config)
    command = arguments.command
    if command == "all":
        for stage in AUTOMATIC_STAGES:
            print(f"== {stage}", flush=True)
            run_stage(stage, project)
    elif command in STAGE_HELP:
        run_stage(command, project)
    elif command in ("approve", "passage", "status"):
        run_review_command(command, project, arguments)
    elif command == "relisten":
        importlib.import_module("openrouter_transcribe.relisten").print_relisten(
            project, arguments.chunk, arguments.moment)
    elif command == "cost":
        costs = ledger_cost(ledger_path(project))
        for model, cost in sorted(costs.items()):
            print(f"{model}: ${cost:.4f}")
        print(f"total: ${sum(costs.values()):.4f}")


def run_review_command(command: str, project: Project, arguments: argparse.Namespace) -> None:
    review = importlib.import_module("openrouter_transcribe.review")
    if command == "approve":
        review.approve(project, arguments.chunks, arguments.note)
    elif command == "passage":
        review.print_passages(project, arguments.chunk, arguments.phrase)
    else:
        review.print_status(project)


if __name__ == "__main__":
    main()
