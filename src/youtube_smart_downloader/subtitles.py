"""Clip converted SubRip cues without losing cues that cross a cut boundary."""

from __future__ import annotations

import re


_TIMING = re.compile(
    r"^(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+"
    r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})(.*)$"
)


def clip_subrip(text: str, start: float, end: float | None) -> str:
    def milliseconds(parts: tuple[str, ...]) -> int:
        h, m, s, ms = map(int, parts)
        return ((h * 60 + m) * 60 + s) * 1000 + ms

    def timestamp(value: int) -> str:
        seconds, ms = divmod(value, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

    offset = round(start * 1000)
    limit = round(end * 1000) if end is not None else None
    cues: list[str] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.splitlines()
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = _TIMING.fullmatch(lines[timing_index])
        if not match:
            raise ValueError("Invalid converted subtitle timing")
        cue_start = max(offset, milliseconds(match.groups()[:4]))
        cue_end = milliseconds(match.groups()[4:8])
        if limit is not None:
            cue_end = min(limit, cue_end)
        if cue_end <= cue_start:
            continue
        timing = (
            f"{timestamp(cue_start - offset)} --> {timestamp(cue_end - offset)}{match.group(9)}"
        )
        cues.append("\n".join([str(len(cues) + 1), timing, *lines[timing_index + 1 :]]))
    return "\n\n".join(cues) + ("\n" if cues else "")
