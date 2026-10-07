"""Stage 4: a second, different listening model; used only to cross-check the first."""

from openrouter_transcribe.config import Project
from openrouter_transcribe.listen import run_with


def run(project: Project) -> None:
    run_with(project, "second", "second")
