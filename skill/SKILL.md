---
name: openrouter-transcribe
description: Use when a long recording (workshop, meeting, interview day, podcast, lecture) must become a complete, reviewed transcript with the right speaker names - "transcribe the recording", "transcript of the workshop", "who said what", "assign speaker names", "Transkript", "Mitschrift aus der Aufnahme" - via OpenRouter, in resumable batches, so that nothing gets lost. Also for recording a session losslessly beforehand.
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
About 1.3 USD per recorded hour.

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
foreground, never end the turn waiting on background work. Then spot-check: read three
reviewed chunks yourself, and `$OT status` must show 0 pending.

## 6. Assemble and verify

```bash
$OT assemble && $OT cost
```

Verify before reporting: word count of the `.md` against the drafts (should be within 10%),
the speaker shares in the `.md` header, the first five minutes of the intro round correct by
name, `[inaudible]` count. Commit the project folder (audio stays out of git).
