"""An interrupted system-audio recording must stay decodable (2026-11-23 MA53: lid closed, no moov index)."""

import re
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "skill" / "scripts"
SOURCE = SCRIPTS / "sysaudio.swift"
BINARY = SCRIPTS / "sysaudio"
MIN_SECONDS = 3.0


def test_source_writes_fragments_and_handles_interruptions() -> None:
    src = SOURCE.read_text()
    assert re.search(r"movieFragmentInterval\s*=", src), "no movieFragmentInterval: moov only on finish"
    assert "fileType: .m4a" not in src, ".m4a cannot carry fragments, use .mp4"
    assert "SIGTERM" in src, "SIGTERM must finalise the file"
    assert "willSleepNotification" in src and "didWakeNotification" in src
    assert '"SLEEP' in src and '"WAKE' in src, "sleep/wake must be logged"
    stop_err = src.split("didStopWithError")[1].split("func stop")[0]
    assert "finish" in stop_err.lower(), "didStopWithError must finalise the writer"


def test_recorder_scripts_guard_against_sleep() -> None:
    start = (SCRIPTS / "record-start.sh").read_text()
    stop = (SCRIPTS / "record-stop.sh").read_text()
    assert "caffeinate -dims" in start and "caffeinate_pid" in start
    assert "plug in power" in start
    assert ".mp4" in start and ".m4a" not in start
    assert "SLEEP" in stop and "died before stop" in stop


def test_killed_recording_is_still_decodable(tmp_path: Path) -> None:
    out = tmp_path / "sys.mp4"
    log = tmp_path / "sysaudio.log"
    with log.open("w") as fh:
        proc = subprocess.Popen([str(BINARY), str(out)], stdout=fh, stderr=subprocess.STDOUT)
        try:
            for _ in range(50):
                if "recording" in log.read_text() or proc.poll() is not None:
                    break
                time.sleep(0.2)
            if proc.poll() is not None or "recording" not in log.read_text():
                pytest.skip(f"sysaudio did not start (Screen Recording permission or display asleep?): {log.read_text()!r}")
            time.sleep(6)
            proc.send_signal(signal.SIGKILL)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
    assert out.exists() and out.stat().st_size > 0
    probe = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-f", "null", "-"],
        capture_output=True, text=True, timeout=60,
    )
    assert probe.returncode == 0 and not probe.stderr.strip(), probe.stderr
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, timeout=60,
    )
    assert float(dur.stdout.strip()) > MIN_SECONDS, dur.stdout + dur.stderr
