# openrouter-transcribe

Turn hours of recorded talk (a workshop, a meeting, an interview day) into a **complete,
reviewed, speaker-named transcript**: one Markdown file to read and one JSONL file to analyse.

* **Nothing gets lost.** The recordings are checksum-verified and only ever read. They are cut
  into chunks with no gap and no overlap (asserted), at the quietest moment near each cut.
  Every chunk is heard by four models. Every minute where a draft heard speech and the transcript
  has little is flagged. An auditor model hears every chunk again and lists what is missing.
  Assembly refuses while any chunk is unreviewed.
* **The right names.** The listening model labels speakers from context ("Ben, what do you
  think?"). Local voice fingerprints, enrolled from each person's own introduction, check every
  turn against the actual voice. When the two disagree, the stronger evidence wins and the turn
  is flagged.
* **In batches, resumable, cheap.** Chunks run in parallel. Every result is written atomically,
  so any stage can be killed and rerun, and it only redoes what is missing. Every API call is in
  a cost ledger. 8.4 hours of workshop audio cost 12.05 USD for stages 1-7 (half of it the
  second listener), plus 5.87 USD for 98 targeted re-listens.

All models run through [OpenRouter](https://openrouter.ai). The voice fingerprints run locally
([sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)); no account, no gated models, no audio
leaves the machine for that step.

## Install

```bash
git clone https://github.com/franzenzenhofer/openrouter-transcribe
cd openrouter-transcribe && uv sync          # needs ffmpeg on PATH
```

## Use

```bash
cp examples/transcript.example.toml /path/to/project/transcript.toml   # edit it
cd /path/to/project
export OPENROUTER_API_KEY=sk-or-...          # a key with a spending limit
OT="uv run --project /path/to/openrouter-transcribe openrouter-transcribe"
$OT all              # stages 1-7, each resumable
$OT status           # what is left to review
$OT passage 12 "two or three words"          # how every listener heard a passage
$OT relisten 12 03:10                          # a strong model hears 30 s around a moment
$OT approve 12 --note "inserted the answer at 03:10 (audit); Ben -> Ana at 05:02"
$OT assemble         # <output>.md + <output>.json + <output>.jsonl
$OT cost
```

## Stages

| # | Stage | What it does | Output under `work/` |
|---|---|---|---|
| 1 | `prepare` | sha256 of every original, cuts at quiet moments, asserts full coverage | `manifest.json`, `chunks/` |
| 2 | `draft` | two speech-to-text drafts per chunk (Whisper large-v3, Deepgram Nova-3) | `raw/<model>/` |
| 3 | `listen` | a listening model hears the audio with both drafts, writes turns + speaker + basis | `listen/` |
| 4 | `second` | a different listening model, same task, as a cross-check | `second/` |
| 5 | `voices` | pins turn starts to word timing, embeds every turn, enrols people, names turns | `voices/` |
| 6 | `check` | review file per chunk: numbers, length, coverage gaps, speaker conflicts | `final/`, `review-report.md` |
| 7 | `audit` | a model hears each chunk against its review file: omissions, wrong speakers | `final/` (review.audit) |
| 8 | review | a person or an agent works through each review file (see `skill/REVIEW-BRIEF.md`) and runs `approve` | `final/` |
| 8b | `relisten` | for passages nobody settled: a strong model hears 30 s of the original audio | `relisten.jsonl` |
| 9 | `assemble` | Markdown, one JSON document and JSONL; refuses while a chunk is unreviewed | `<output>.md`, `.json`, `.jsonl` |

## How a turn gets its name

`voices` embeds each turn with two speaker-verification models (TitaNet large and ERes2Net,
averaged) and compares it with each person's voice centroid. Centroids start from the samples in
`transcript.toml`, then are re-estimated three times from turns where voice and listener agree.

| Situation | Name |
|---|---|
| listener said "several people" | several |
| turn shorter than `short_turn_seconds` | listener's name (too little audio to judge) |
| voice and listener agree | that name (`agree`) |
| listener is sure from context (`named`), voice only weakly disagrees | listener's name, flagged |
| voice is clear (similarity >= `min_similarity`, margin >= `min_margin`) | voice's name, flagged if the listener heard someone else |
| voice unclear, listener gave a name | listener's name, flagged |
| neither | unclear |

Long turns are also scanned window by window; a stretch that clearly sounds like someone else
is flagged as a possible speaker change. `work/voices/report.md` shows how well the voices
separate and every disagreement.

## Lessons learned (two full-day workshops, 17 hours)

1. **Record lossless, in segments, supervised.** An ffmpeg recording dropped 12% of its samples
   in tiny fragments; that audio is gone. `record/record-loop.sh` runs sox in 30-minute FLAC
   segments and restarts it if a segment stops growing.
2. **Never touch the originals.** Make them read-only, keep a `SHA256SUMS`, copy them off the
   machine, and let the harness verify the checksum before every run.
3. **Cut at silence, not at the clock.** Cutting mid-word loses that word in both chunks.
4. **No single speech-to-text model is enough.** Whisper invents filler in pauses ("Thank you.",
   "Amen", subtitle credits) and mishears terms; other models skip sentences. A listening model
   with audio plus two drafts, cross-checked by a second listener, gets close to complete.
5. **Models disappear.** Gemini 3.5 Transcribe answered every request with "Provider returned
   400" one week after it transcribed a whole day without trouble. Keep the models in the
   project file and fail loudly.
6. **Do not let a language model name the speakers alone.** Given voice samples, two runs of the
   same chunk gave different names to the same passages. Voice fingerprints are deterministic;
   the language model adds context (names said aloud). Use both and flag disagreement.
7. **Enrol from introductions.** The intro round ("I'm Ben, backend engineer") is the best
   voice sample of the day: one person, their own name, near the start.
8. **Timestamps from a listening model drift by seconds.** Pin each turn start to the word
   timing of a draft (Deepgram gives per-word times) before cutting turn audio for fingerprints.
9. **A reviewer without audio needs an ear.** The audit stage hears the chunk against the review
   file and lists omissions with the exact words; the reviewer applies them.
10. **Review rules beat review taste.** Change a number only when two other listeners agree or
    one listener plus project data confirm it; never paraphrase; log every change in the
    sign-off note.
11. **Everything resumable, everything logged.** Atomic writes per chunk, retries on transient
    HTTP errors only (5xx incl. 520-524, 429), a cost ledger per call.
12. **A capped API key per project.** Long audio runs are cheap but not free; a per-project key
    with a hard limit makes a runaway loop harmless.

## Development

```bash
uv run ruff check . && uv run mypy src tests && uv run pytest -q
```

## License

MIT, see [LICENSE](LICENSE).
