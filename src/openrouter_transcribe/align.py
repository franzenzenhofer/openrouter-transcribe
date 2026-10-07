"""Pin a turn's start to a word timestamp from a draft that has word timing.

Listening models give MM:SS starts that can be off by seconds; voice naming needs the audio of
the turn itself, so the start is moved to where the turn's first words were actually heard.
"""

import re

Word = tuple[str, float]
SEARCH_SECONDS = 15.0
LEADING_WORDS = (3, 2)
TOKEN = re.compile(r"[\w']+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN.findall(text)]


def draft_words(payload: dict[str, object]) -> list[Word]:
    """(token, start) for every word of a draft with word timing; empty if it has none."""
    words = payload.get("words")
    if not isinstance(words, list):
        return []
    found: list[Word] = []
    for word in words:
        for token in tokens(str(word["word"])):
            found.append((token, float(word["start"])))
    return found


def refine_start(text: str, approx: float, words: list[Word]) -> float:
    """Start of the nearest place where the turn's first words occur; else `approx`."""
    wanted = tokens(text)
    for count in LEADING_WORDS:
        if len(wanted) < count:
            continue
        head = wanted[:count]
        hits = [words[index][1] for index in range(len(words) - count + 1)
                if abs(words[index][1] - approx) <= SEARCH_SECONDS
                and [token for token, _ in words[index:index + count]] == head]
        if hits:
            return min(hits, key=lambda start: abs(start - approx))
    return approx


def refined_starts(texts: list[str], approx: list[float], words: list[Word]) -> list[float]:
    """Refined starts that never break chronological order."""
    starts: list[float] = []
    for text, guess in zip(texts, approx, strict=True):
        start = refine_start(text, guess, words) if words else guess
        floor = starts[-1] if starts else 0.0
        starts.append(start if start >= floor else max(guess, floor))
    return starts
