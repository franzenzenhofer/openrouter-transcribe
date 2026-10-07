"""Prompt text and response schemas for the listening and auditing models."""

from typing import Any

from openrouter_transcribe.config import Project
from openrouter_transcribe.plan import format_clock

BASIS_VALUES = ("named", "voice", "guess")

LISTEN_RULES = """\
Rules:
1. AUDIO is the section to transcribe and the only source of truth. Two machine drafts are given
   as aids. Both contain errors: Whisper invents filler in pauses ("Thank you.", "Bye.", "Vielen
   Dank", subtitle credits) and mishears terms; the other draft sometimes skips sentences.
   Write everything that is audibly said, and nothing that is not. Never drop a sentence because
   it is off-topic, small talk or hard to hear.
2. Verbatim, in the language spoken. Never summarize, shorten or paraphrase. Drop only filled
   pauses and pure stutters. Keep false starts that carry meaning.
3. Start a new turn at every speaker change, also for one-word answers ("Yes.", "Exactly.").
   Split long monologues into turns of at most about 60 seconds at natural breaks. Give each turn
   its start time in AUDIO as MM:SS, as exact as you can: the moment the first word starts.
   Turns are in chronological order.
4. Speaker: one of the roster names, or "{unclear}" when you cannot attribute the voice, or
   "{several}" for several people at once. A label is always a name, never a bracketed event.
   "basis" says why: "named" = the speaker is addressed by name, names themselves, or the
   content makes it certain; "voice" = the voice matches the roster description; "guess" =
   anything weaker.
5. Write "{unintelligible}" where speech is audible but cannot be understood. Mark relevant
   non-speech in brackets, e.g. "[laughter]", "[pause]".
6. Spell names and domain terms as in the glossary. Write numbers exactly as spoken; never
   round or correct them.
7. Use "notes" for anything a reviewer must know: unsure passages, crosstalk, audio problems.
   Leave it empty when there is nothing.
"""

TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "start": {"type": "string", "description": "MM:SS in AUDIO"},
        "speaker": {"type": "string"},
        "basis": {"type": "string", "enum": list(BASIS_VALUES)},
        "text": {"type": "string"},
    },
    "required": ["start", "speaker", "basis", "text"],
    "additionalProperties": False,
}

LISTEN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"turns": {"type": "array", "items": TURN_SCHEMA}, "notes": {"type": "string"}},
    "required": ["turns", "notes"],
    "additionalProperties": False,
}


def roster_text(project: Project) -> str:
    return "\n".join(f"- {person.name}: {person.description}" for person in project.people)


def system_prompt(project: Project) -> str:
    rules = LISTEN_RULES.format(unclear=project.unclear, several=project.several,
                                unintelligible=project.unintelligible)
    return (f"You produce the authoritative verbatim transcript of one section of a long "
            f"recording.\n\nSetting:\n{project.setting}\n\nRoster (the people who speak):\n"
            f"{roster_text(project)}\n\nGlossary: {', '.join(project.glossary)}\n\n{rules}")


def timed_draft(payload: dict[str, Any]) -> str:
    """Segments as "[MM:SS] text" lines, or the plain text when a model gives no segments."""
    segments = payload.get("segments") or []
    if not segments:
        return str(payload["text"])
    return "\n".join(f"[{format_clock(float(segment['start']))}] {segment['text'].strip()}"
                     for segment in segments)


def turns_text(turns: list[dict[str, str]]) -> str:
    return "\n".join(f"[{turn['start']}] {turn['speaker']}: {turn['text']}" for turn in turns)
