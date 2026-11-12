"""Shared download requests and whole-second time ranges."""

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class TimeRange:
    start: int = 0
    end: int | None = None

    def __post_init__(self) -> None:
        if type(self.start) is not int or self.start < 0:
            raise ValueError("Start must be a non-negative whole number of seconds")
        if self.end is not None and (type(self.end) is not int or self.end <= self.start):
            raise ValueError("End must be a whole number of seconds after start")

    @property
    def key(self) -> str:
        return f"{self.start}-{self.end if self.end is not None else 'inf'}"

    def duration(self, source_duration: float | None) -> float:
        if source_duration is None or not math.isfinite(source_duration) or source_duration <= 0:
            raise ValueError("Cannot download a time range without a known video duration")
        if self.start >= source_duration or (self.end is not None and self.end > source_duration):
            raise ValueError("The requested time range is outside the video duration")
        return (self.end if self.end is not None else source_duration) - self.start


def parse_time(value: str) -> int:
    value = value.strip()
    if not re.fullmatch(r"[0-9]+(?::[0-9]{1,2}){0,2}", value):
        raise ValueError("Use whole seconds, MM:SS or HH:MM:SS")
    parts = [int(part) for part in value.split(":")]
    if len(parts) > 1 and any(part > 59 for part in parts[-2:]):
        raise ValueError("Minutes and seconds must be between 0 and 59")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def parse_time_range(start: str = "", end: str = "") -> TimeRange | None:
    if not start.strip() and not end.strip():
        return None
    result = TimeRange(
        parse_time(start) if start.strip() else 0, parse_time(end) if end.strip() else None
    )
    return None if result == TimeRange() else result


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    time_range: TimeRange | None = None

    def __post_init__(self) -> None:
        if self.time_range == TimeRange():
            object.__setattr__(self, "time_range", None)
