# Review brief - one chunk at a time

You review one machine transcript chunk of a long recording. You have no audio, but the audit
model had it: `review.audit.findings` lists what it heard differently. Your job: apply what is
supported, fix what a careful reader can catch, keep everything else as heard, and sign off.

## The file

`work/final/NNN.json` (NNN = chunk number, zero-padded):

* `chunk` - times of the chunk. Do not touch.
* `review` - automatic findings (below). Do not edit, except through `approve`.
* `turns` - the transcript. You edit `speaker` and `text`, and you may insert or remove turns.
  An inserted turn needs `start` (MM:SS in the chunk) and `start_seconds`, placed in order.
  Other keys (`heard`, `decided_by`, `similarity`, `margin`, `voice_flags`) are evidence; keep.

Compare a passage across all listeners:

```bash
openrouter-transcribe passage NNN "two or three words"
```

It prints the passage as heard by `final`, `second`, `whisper` and `stt`.

When no listener settles a passage (every source differs, or only the auditor has it), let a
strong model hear the original audio around that moment (about 0.06 USD per call):

```bash
openrouter-transcribe relisten NNN MM:SS
```

Apply what it hears when it is clear and fits at least one draft or the context; say
"relisten" in the sign-off note. Its MM:SS times can be off; place text by the words around it.

## What to check, in this order

1. **`review.audit.findings`** (the auditor heard the audio):
   * `omission`: insert the `heard` words as a new turn (or into the right turn) at `at`,
     speaker as given if it is a roster name. Check with `passage` that at least one draft
     has those words; if none has them and they read like invention, skip and note it.
   * `wrong_speaker`: change the speaker if the voice evidence does not contradict it
     (`decided_by` is `agree` with a high `similarity`) - otherwise keep and note it.
   * `misheard`: apply if `passage` shows another listener with the same words, or the
     project data / glossary confirms them.
   * `invented`: remove only if no draft has the words.
   * `merged_turns`: split the turn; the new turn gets a `start_seconds` inside the old turn.
2. **`voice_flags` on turns**: "listener heard X" / "voice suggests X" / "possible speaker
   change at Ns (X)". Decide from content: who is addressed in the turn before, who answers,
   who presents vs. asks. Split a turn at a speaker change when the text shows it.
3. **`review.speaker_conflicts`** (the second listener named someone else): same rule.
4. **`review.unsupported_numbers` / `missing_numbers`**: change a number only if two other
   listeners agree on another value, or one does and project data confirms it.
5. **`possible gap` flags**: find the passage with `passage`; insert what the drafts heard
   if it is missing (wording from `second`), as its own turn.
6. **Read every turn.** Fix only clear errors: misheard glossary terms, filler a draft
   invented ("Thank you." alone in a pause), a sentence repeated in a loop, two speakers glued
   into one turn.

## Never

* Rephrase, shorten, summarize, translate or tidy spoken language. It is verbatim.
* Rename a speaker to a name outside the roster. Change `start` of existing turns.
* Touch files outside `work/final/`, delete files, or run any stage other than `passage`,
  `relisten`, `approve` and `status`.

## Sign-off

```bash
python3 -c "import json; json.load(open('work/final/NNN.json'))"
openrouter-transcribe approve N --note "inserted omission 03:10 (audit, whisper has it); \
Ben -> Ana at 05:02 (audit + addressed by name); none else"
```

Run every command in the foreground. Report one line per chunk: what changed and why, and
anything you saw but could not settle.
