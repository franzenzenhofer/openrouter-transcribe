"""Pure checks of one chunk's transcript against the other listeners. Nothing is changed here;
every finding becomes a flag for the reviewer."""

import re
import statistics
from collections import Counter
from dataclasses import dataclass

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
THOUSANDS = re.compile(r"[.,](?=\d{3}(?:\D|$))")
SNIPPET_RADIUS = 60
COVERAGE_LOW = 0.8
COVERAGE_HIGH = 1.3
MINIMUM_SUPPORT = 2
GAP_BIN_SECONDS = 60.0
GAP_MINIMUM_WORDS = 25
GAP_RATIO = 0.5
CONFLICT_MINIMUM_WORDS = 15
PREVIEW = 140

Span = tuple[float, float, str]


def normalize_number(token: str) -> str:
    """"6.544" / "6,544" -> "6544"; "14,3" -> "14.3", so all listeners compare."""
    return THOUSANDS.sub("", token).replace(",", ".")


def numbers_in(text: str) -> set[str]:
    found = (normalize_number(match.group()) for match in NUMBER.finditer(text))
    return {number for number in found if len(number) > 1}


def snippet(text: str, number: str) -> str:
    for match in NUMBER.finditer(text):
        if normalize_number(match.group()) == number:
            start = max(0, match.start() - SNIPPET_RADIUS)
            return "..." + text[start:match.end() + SNIPPET_RADIUS].replace("\n", " ") + "..."
    raise ValueError(f"{number} does not occur in the text")


@dataclass(frozen=True)
class Comparison:
    words: dict[str, int]
    coverage: float
    unsupported: list[str]
    missing: list[str]

    @property
    def flags(self) -> list[str]:
        flags = []
        if self.coverage < COVERAGE_LOW:
            flags.append(f"short: {self.coverage:.0%} of the other listeners' median length")
        if self.coverage > COVERAGE_HIGH:
            flags.append(f"long: {self.coverage:.0%} of the other listeners' median length")
        if self.unsupported:
            flags.append(f"{len(self.unsupported)} numbers no other listener heard")
        if self.missing:
            flags.append(f"{len(self.missing)} numbers heard by {MINIMUM_SUPPORT}+ others, "
                         "absent here")
        return flags


def compare(final: str, others: dict[str, str]) -> Comparison:
    """`others` maps a listener name to its text of the same chunk."""
    other_numbers = {name: numbers_in(text) for name, text in others.items()}
    mine = numbers_in(final)
    heard_elsewhere: set[str] = set().union(*other_numbers.values())
    support = Counter(number for found in other_numbers.values() for number in found)
    words = {name: len(text.split()) for name, text in others.items()}
    return Comparison(
        words={"final": len(final.split()), **words},
        coverage=len(final.split()) / max(1.0, statistics.median(words.values())),
        unsupported=sorted(mine - heard_elsewhere),
        missing=sorted(number for number, count in support.items()
                       if count >= MINIMUM_SUPPORT and number not in mine),
    )


def words_per_bin(spans: list[Span], seconds: float) -> list[float]:
    """Words per GAP_BIN_SECONDS, each span's words spread evenly over its duration."""
    bins = [0.0] * (int(seconds // GAP_BIN_SECONDS) + 1)
    for start, end, text in spans:
        count = len(text.split())
        end = max(end, start + 0.01)
        for index in range(len(bins)):
            low, high = index * GAP_BIN_SECONDS, (index + 1) * GAP_BIN_SECONDS
            overlap = max(0.0, min(end, high) - max(start, low))
            bins[index] += count * overlap / (end - start)
    return bins


def gaps(final: list[Span], reference: list[Span], seconds: float) -> list[str]:
    """Minutes where the reference draft heard speech and the transcript has much less."""
    mine, theirs = words_per_bin(final, seconds), words_per_bin(reference, seconds)
    return [f"possible gap {int(index * GAP_BIN_SECONDS // 60):02d}:00-"
            f"{int((index + 1) * GAP_BIN_SECONDS // 60):02d}:00: {mine[index]:.0f} words here, "
            f"{theirs[index]:.0f} in the draft"
            for index in range(len(mine))
            if theirs[index] >= GAP_MINIMUM_WORDS and mine[index] < GAP_RATIO * theirs[index]]


def speaker_at(turns: list[tuple[float, str]], seconds: float) -> str:
    """Who speaks at a moment according to (start, speaker) turns of another listener."""
    current = turns[0][1] if turns else ""
    for start, speaker in turns:
        if start > seconds:
            break
        current = speaker
    return current


def conflicts(final: list[tuple[float, float, str, str]], second: list[tuple[float, str]],
              people: set[str]) -> list[dict[str, str]]:
    """Longer turns where the second listener names a different person."""
    found = []
    for start, end, speaker, text in final:
        other = speaker_at(second, (start + end) / 2)
        if len(text.split()) >= CONFLICT_MINIMUM_WORDS and other != speaker \
                and other in people and speaker in people:
            found.append({"start": f"{start:.0f}s", "final": speaker, "second": other,
                          "text": text[:PREVIEW]})
    return found
