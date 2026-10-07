"""The project file (transcript.toml): what was recorded, who speaks, which models listen."""

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MODELS = {
    "whisper": "openai/whisper-large-v3",
    "stt": "deepgram/nova-3",
    "listener": "google/gemini-3.8-flash",
    "second": "google/gemini-3.1-pro-preview",
    "auditor": "google/gemini-3.8-flash",
}
DEFAULT_EMBEDDING_MODELS = (
    "nemo_en_titanet_large.onnx",
    "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
)
FILLERS_BY_LANGUAGE = {
    "de": [r"\b[Ää]h+m?\b[,.]?\s*"],
    "en": [r"\b(?:[Uu]h+|[Uu]hm+|[Ee]rm+)\b[,.]?\s*"],
}
UNINTELLIGIBLE_BY_LANGUAGE = {"de": "[unverständlich]", "en": "[inaudible]"}


@dataclass(frozen=True)
class Source:
    """One original recording. The harness only ever reads it."""

    key: str
    title: str
    path: Path
    sha256: str
    wall_start: datetime
    wall_end: datetime
    note: str = ""

    @property
    def wall_seconds(self) -> float:
        return (self.wall_end - self.wall_start).total_seconds()


@dataclass(frozen=True)
class Sample:
    """A stretch of a source where only this person speaks (seconds into the source)."""

    source: str
    start: float
    end: float


@dataclass(frozen=True)
class Person:
    """`description` is for the listening models; `role` (short) is shown in the transcript."""

    name: str
    description: str
    samples: tuple[Sample, ...] = ()
    role: str = ""


@dataclass(frozen=True)
class Voices:
    """Thresholds for naming a turn by its voice (cosine similarity, averaged over models)."""

    models: tuple[str, ...] = DEFAULT_EMBEDDING_MODELS
    window_seconds: float = 3.0
    hop_seconds: float = 1.5
    silence_dbfs: float = -55.0
    min_similarity: float = 0.45
    min_margin: float = 0.08
    short_turn_seconds: float = 2.5
    change_seconds: float = 6.0
    rounds: int = 3


@dataclass(frozen=True)
class Project:
    root: Path
    title: str
    language: str
    setting: str
    glossary: tuple[str, ...]
    sources: tuple[Source, ...]
    people: tuple[Person, ...]
    models: dict[str, str]
    voices: Voices
    unclear: str
    several: str
    unintelligible: str
    fillers: tuple[str, ...]
    chunk_seconds: float = 480.0
    workers: int = 6
    output: str = "transcript"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(person.name for person in self.people)

    def source(self, key: str) -> Source:
        return next(source for source in self.sources if source.key == key)


def parse_clock(stamp: str) -> float:
    """Seconds from "SS", "MM:SS" or "H:MM:SS"."""
    seconds = 0.0
    for part in stamp.strip().split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def _source(root: Path, raw: dict[str, Any]) -> Source:
    start, end = datetime.fromisoformat(raw["wall_start"]), datetime.fromisoformat(raw["wall_end"])
    if start.tzinfo is None or end <= start:
        raise ValueError(f"source {raw['key']}: wall times need a timezone and end > start")
    return Source(key=raw["key"], title=raw["title"], path=(root / raw["file"]).resolve(),
                  sha256=raw["sha256"], wall_start=start, wall_end=end, note=raw.get("note", ""))


def _person(raw: dict[str, Any], keys: set[str]) -> Person:
    samples = tuple(Sample(item["source"], parse_clock(item["start"]), parse_clock(item["end"]))
                    for item in raw.get("samples", []))
    for sample in samples:
        if sample.source not in keys or sample.end <= sample.start:
            raise ValueError(f"{raw['name']}: bad sample {sample}")
    return Person(name=raw["name"], description=raw["description"], samples=samples,
                  role=raw.get("role", ""))


def _voices(raw: dict[str, Any]) -> Voices:
    """Only known keys; models as a tuple, everything else as numbers."""
    unknown = set(raw) - set(Voices.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown [voices] keys: {sorted(unknown)}")
    defaults = Voices()
    numbers = {key: type(getattr(defaults, key))(value)
               for key, value in raw.items() if key != "models"}
    models = tuple(raw.get("models", defaults.models))
    return Voices(models=models, **numbers)


def load(path: Path) -> Project:
    raw = tomllib.loads(path.read_text())
    root = path.resolve().parent
    language = raw["language"]
    sources = tuple(_source(root, item) for item in raw["sources"])
    keys = {source.key for source in sources}
    if len(keys) != len(sources):
        raise ValueError("source keys must be unique")
    people = tuple(_person(item, keys) for item in raw["people"])
    labels = raw.get("labels", {})
    return Project(
        root=root, title=raw["title"], language=language, setting=raw["setting"].strip(),
        glossary=tuple(raw.get("glossary", [])), sources=sources, people=people,
        models={**DEFAULT_MODELS, **raw.get("models", {})},
        voices=_voices(raw.get("voices", {})),
        unclear=labels.get("unclear", "Unclear"), several=labels.get("several", "Several"),
        unintelligible=raw.get("unintelligible", UNINTELLIGIBLE_BY_LANGUAGE.get(language, "[?]")),
        fillers=tuple(raw.get("fillers", FILLERS_BY_LANGUAGE.get(language, []))),
        chunk_seconds=float(raw.get("chunk_seconds", 480.0)), workers=int(raw.get("workers", 6)),
        output=raw.get("output", "transcript"),
    )
