---
name: openrouter-transcribe
description: Use when a long recording (workshop, meeting, interview day, podcast, lecture) must become a complete, reviewed transcript with the right speaker names - "transcribe the recording", "transcript of the workshop", "who said what", "assign speaker names", "Transkript", "Mitschrift aus der Aufnahme" - via OpenRouter, in resumable batches, so that nothing gets lost. Also for recording a session losslessly beforehand. Also for recording a LIVE CALL on this Mac (Teams, Zoom, Meet) incl. with AirPods and transcribing it cheaply - "record this call", "start recording", "record audio and my screen", "AirPods", "Teams call recording", "Call aufnehmen", "Aufnahme starten".
---

# openrouter-transcribe

Tool: `~/dev/openrouter-transcribe` (github.com/franzenzenhofer/openrouter-transcribe). Read its
`README.md` once; it has the stages, the naming rules and the lessons learned.

```bash
OT="uv run --project ~/dev/openrouter-transcribe openrouter-transcribe -c transcript.toml"
```

## Before the session (if it is not recorded yet)

Copy `~/dev/openrouter-transcribe/record/` into the project's `recordings/` and use
`start-recording.sh` / `status.sh` / `stop-recording.sh` / `finish-recording.sh`. Lossless,
30-minute segments, supervised. Copy the files off the machine the same day.

## Live call on this Mac (Teams/Zoom/Meet), also with AirPods - cheap path

Why: with AirPods the remote voices never reach any microphone, and ffmpeg/avfoundation cannot capture
system output. `scripts/sysaudio.swift` (ScreenCaptureKit) captures system audio with no driver
(no BlackHole). Mics + screen go through ffmpeg. Both start from ONE script (lesson: starting them
separately lost the first minute of the remote side). Scripts live in `~/.claude/skills/openrouter-transcribe/scripts/`
(`S=~/.claude/skills/openrouter-transcribe/scripts`).

Runbook:
1. Once per terminal app: Screen Recording permission (System Settings > Privacy & Security), needed
   by ffmpeg screen capture AND ScreenCaptureKit. Without it both exit at start and the script says so.
2. Start (before the call, or the moment it begins):
   `bash $S/record-start.sh --out <dir> --title <name>` (`--no-video` for audio only; `--mic1 REGEX`,
   `--mic2 REGEX`, `--screen REGEX` override the default device-name matches AirPods / MacBook.*Microphone /
   Capture screen). Devices are found by NAME from `ffmpeg -f avfoundation -list_devices true -i ""`, never by
   index (the AirPods index changes). It compiles `sysaudio` on first use (`swiftc -O`), launches ffmpeg and
   sysaudio together and writes `<dir>/record.state` (PIDs, start timestamps, offset).
3. Stop: `bash $S/record-stop.sh --out <dir>`. SIGINT to both (files are finalised), waits, then prints duration +
   volumedetect per track. Exit 3 and "FAILED" if a file is missing or a track has mean below -60 dB. Do not
   transcribe a failed recording; if it fails during the call, fix it then (AirPods connected? Mac output
   really set to them? permission?).
4. Mix: `bash $S/mix.sh --main <main.mkv> --sys <sysaudio.m4a> --out <dir>/mix --offset-ms <sysaudio_start_ms - ffmpeg_start_ms>`
   (both values are in the `record.state.stopped-*` file; the start script also prints the offset).
   Result: STEREO 16 kHz, left = me (mic track 1), right = remote (system audio), mp3 chunks of 18 min at
   32 kbps (about 4.3 MB each). `--with-mic2` adds the built-in mic to the left channel only if track 1 is weak.
5. Transcribe: `export OPENROUTER_API_KEY=...` (never hardcoded; the script exits with a clear error if missing), then
   `python3 -I $S/transcribe.py --chunks-dir <dir>/mix --out <dir>/transcript.md --title "..." --language German --participants "Franz Enzenhofer (left channel); Name (right channel)"`.
   One google/gemini-2.5-flash call per chunk, prompt asks for verbatim `[mm:ss] Name: text` lines and tells Gemini
   which channel is who. Measured: 17 min = 4.2 MB = 0.046 USD.

Lessons:
* Mono-mixing mic + system audio echoes duplicate lines (the remote voice is on both when speakers are used),
  so keep them as separate channels for speaker attribution.
* Keep each upload under 5 MB (metered-connection guard allows local uploads under 5 MB); longer calls become
  several chunks (mix.sh and transcribe.py both enforce it).
* Timestamps in a chunk's transcript are relative to that clip; the header gives the clip start.
* Do not run this on a metered connection if the upload would exceed the guard; chunks stay below it.
* Test of the scripts: 8 s run, files finalised, ffprobe readable; silence is detected and reported by record-stop.sh.

## 1. Project file

Create `<project>/NN-transcript/transcript.toml` from `examples/transcript.example.toml`.
Client data (names, setting, glossary, times) lives only there, never in the tool repo.

* `sources`: each recording with `sha256` (`shasum -a 256`), wall-clock start and end.
* `setting`, `glossary`: occasion, language, room, terms and names to spell right.
* `people`: everyone who speaks, with a description (role, gender, accent, distance to the
  mic) and `samples`. Find the samples: send the first 20-25 minutes (cut with ffmpeg to a
  16 kHz mp3) to `google/gemini-3.8-flash` and ask for every self-introduction with MM:SS start
  and end and a verbatim quote. Use 10-30 s of each person's own introduction.
* A person who did not introduce themselves gets no samples; they are enrolled from turns where
  the listener is sure (`named`).

## 2. Key

One capped OpenRouter key per project (management key creates it: `POST /api/v1/keys` with
`{"name": "<project>-transcript", "limit": 30}`), stored outside the repo, chmod 600.
About 1.45 USD per recorded hour for stages 1-7 (8.4 h cost 12.05 USD; half of it is the Pro second listener), plus about 0.06 USD per `relisten` (98 calls added 5.87 USD).

## 3. Run

```bash
export OPENROUTER_API_KEY=$(cat <key file>)
nohup $OT all > work/all.log 2>&1 &     # prepare, draft, listen, second, voices, check, audit
```

Arm a watchdog (Monitor) on the log that fires on `jobs done`, `FAILED`, `Traceback` and on
15 minutes without growth. A failed stage is rerun as is: only the missing chunks are redone.
If a model is gone (HTTP 400 "Provider returned 400" on every call), swap it in `[models]`.

## 4. Check the voices before reviewing

Read `work/voices/report.md`:
* centroid similarities between different people should be well below 0.6;
* "turns the listener marked named" agreement should be 85% or higher;
* the share of the main speaker should match what you know.
If a person's centroid is weak (few samples), add samples and rerun `voices` (delete
`work/voices/assignments/` first; embeddings are cached), then `check` (move `work/final/` to
trash first only if nothing was reviewed yet).

## 5. Review every chunk

Dispatch review subagents (about 8 chunks each, in parallel) with `skill/REVIEW-BRIEF.md` as
their brief, the project file path and their chunk numbers. Tell each: run commands in the
foreground, never end the turn waiting on background work. Collect every passage the reviewers
could not settle and run `$OT relisten N MM:SS` on each; apply the clear ones. Then spot-check: read three
reviewed chunks yourself, and `$OT status` must show 0 pending.

## 6. Assemble and verify

```bash
$OT assemble && $OT cost
```

Verify before reporting: word count of the `.md` against the drafts (should be within 10%),
the speaker shares in the `.md` header, the first five minutes of the intro round correct by
name, `[inaudible]` count. Commit the project folder (audio stays out of git).
