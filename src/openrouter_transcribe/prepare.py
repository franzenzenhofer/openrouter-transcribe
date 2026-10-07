"""Stage 1: verify the originals byte for byte and cut them into chunks at quiet moments."""

from openrouter_transcribe.audio import cut_mp3, probe_seconds, read_pcm, sha256_of
from openrouter_transcribe.config import Project, Source
from openrouter_transcribe.plan import (
    Chunk,
    assert_full_coverage,
    build_chunks,
    quietest_offset,
    target_cuts,
)
from openrouter_transcribe.store import chunk_audio, load_chunks, manifest_path, write_json

CUT_SEARCH_SECONDS = 40.0
QUIET_WINDOW_SECONDS = 0.4
ANALYSIS_RATE = 8000
DURATION_TOLERANCE_SECONDS = 0.5


def verify_source(source: Source) -> float:
    """Fail loudly if an original is missing or differs from the recorded checksum."""
    actual = sha256_of(source.path)
    if actual != source.sha256:
        raise RuntimeError(f"{source.path.name}: sha256 {actual} differs from {source.sha256}")
    return probe_seconds(source.path)


def refine_cut(source: Source, cut: float) -> float:
    """Move a planned cut to the quietest moment nearby."""
    window_start = cut - CUT_SEARCH_SECONDS
    samples = read_pcm(source.path, window_start, 2 * CUT_SEARCH_SECONDS, ANALYSIS_RATE)
    return window_start + quietest_offset(samples, ANALYSIS_RATE, QUIET_WINDOW_SECONDS)


def plan_chunks(project: Project, totals: dict[str, float]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for source in project.sources:
        total = totals[source.key]
        cuts = [refine_cut(source, cut) for cut in target_cuts(total, project.chunk_seconds)]
        chunks.extend(build_chunks(source, cuts, total, first=len(chunks) + 1))
    assert_full_coverage(chunks, totals)
    return chunks


def cut_chunk(project: Project, chunk: Chunk) -> None:
    target = chunk_audio(project, chunk)
    if not target.exists():
        cut_mp3(project.source(chunk.source).path, chunk.start, chunk.end, target)
    seconds = probe_seconds(target)
    if abs(seconds - chunk.seconds) > DURATION_TOLERANCE_SECONDS:
        raise RuntimeError(f"chunk {chunk.name}: {seconds:.2f}s, expected {chunk.seconds:.2f}s")


def run(project: Project) -> None:
    totals: dict[str, float] = {}
    for source in project.sources:
        totals[source.key] = verify_source(source)
        print(f"verified {source.path.name} ({totals[source.key] / 3600:.2f} h)", flush=True)
    if manifest_path(project).exists():
        chunks = load_chunks(project)
        assert_full_coverage(chunks, totals)
    else:
        chunks = plan_chunks(project, totals)
        write_json(manifest_path(project), {"chunks": [chunk.to_json() for chunk in chunks]})
    for chunk in chunks:
        cut_chunk(project, chunk)
    hours = sum(chunk.seconds for chunk in chunks) / 3600
    print(f"{len(chunks)} chunks, {hours:.2f} h of audio", flush=True)
