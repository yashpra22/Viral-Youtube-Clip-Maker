"""Convert yt-dlp's JSON3 captions into AutoClip's word-timed transcript."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .transcript import Segment, Transcript, Word

_WORD = re.compile(r"\S+")


def load_json3(path: Path) -> Transcript:
    """Read JSON3 captions, preserving supplied word offsets when available.

    Some YouTube caption events contain one word per segment with offsets;
    others contain a phrase. Phrase timings are divided across its words so
    downstream word-indexed clipping and captions can still operate.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    transcript = Transcript(
        language=path.stem.rsplit(".", 1)[-1], model="youtube", source="youtube"
    )

    for event in payload.get("events", []):
        pieces = [
            segment
            for segment in event.get("segs", [])
            if isinstance(segment.get("utf8"), str) and segment["utf8"].strip()
        ]
        if not pieces:
            continue

        event_start = float(event.get("tStartMs", 0)) / 1000
        event_end = event_start + float(event.get("dDurationMs", 0)) / 1000
        segment_words: list[tuple[str, float, float]] = []
        for index, piece in enumerate(pieces):
            text = piece["utf8"].replace("\n", " ").strip()
            words = [match.group(0) for match in _WORD.finditer(text)]
            if not words:
                continue
            start = event_start + float(piece.get("tOffsetMs", 0)) / 1000
            if index + 1 < len(pieces):
                end = event_start + float(pieces[index + 1].get("tOffsetMs", 0)) / 1000
            else:
                end = event_end
            if end <= start:
                end = start + max(0.18, len(words) * 0.22)
            span = end - start
            weights = [max(1, len(word.strip(".,!?;:'\"()[]{}"))) for word in words]
            total_weight = sum(weights)
            cursor = start
            for word, weight in zip(words, weights, strict=True):
                word_end = cursor + span * weight / total_weight
                segment_words.append((word, cursor, word_end))
                cursor = word_end

        if not segment_words:
            continue
        first_word = len(transcript.words)
        transcript.words.extend(Word(text, start, end) for text, start, end in segment_words)
        start = segment_words[0][1]
        end = segment_words[-1][2]
        text = " ".join(word for word, _, _ in segment_words)
        transcript.segments.append(
            Segment(
                text=text,
                start=start,
                end=end,
                first_word=first_word,
                last_word=len(transcript.words) - 1,
            )
        )

    if not transcript.words:
        raise ValueError(f"No usable captions found in {path.name}.")
    return transcript


def find_json3(directory: Path) -> Path | None:
    """Find the best English JSON3 caption sidecar in a source directory."""
    candidates = sorted(
        directory.glob("*.json3"),
        key=lambda path: ("en" not in path.name.lower(), path.name),
    )
    return candidates[0] if candidates else None
