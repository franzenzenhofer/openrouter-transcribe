"""Run independent per-chunk jobs in parallel; every failure is reported, none is swallowed."""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed


def job_name(job: object) -> str:
    """"017" for a chunk, "017 openai/whisper-large-v3" for a (chunk, model) job."""
    parts = job if isinstance(job, tuple) else (job,)
    return " ".join(str(getattr(part, "name", part)) for part in parts)


def run_all[T](jobs: Sequence[T], work: Callable[[T], str], workers: int, label: str) -> None:
    """Prints one line per finished job; raises at the end if any job failed."""
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                print(future.result(), flush=True)
            except Exception as error:
                failures.append(f"{job_name(futures[future])}: {error}")
                print(f"FAILED {job_name(futures[future])}: {error}", flush=True)
    if failures:
        raise RuntimeError(f"{label}: {len(failures)} of {len(jobs)} jobs failed; rerun to "
                           "retry only those:\n" + "\n".join(failures))
    print(f"{label}: {len(jobs)} jobs done", flush=True)
