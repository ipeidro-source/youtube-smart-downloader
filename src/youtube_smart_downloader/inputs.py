"""Pure YouTube input classification and reviewed TXT imports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import parse_qs, urlparse

from .core import valid_youtube_url


@dataclass(frozen=True)
class YouTubeInput:
    kind: Literal["video", "playlist", "ambiguous"]
    video_url: str = ""
    playlist_url: str = ""


def classify_url(url: str) -> YouTubeInput:
    if not valid_youtube_url(url):
        raise ValueError("Enter a YouTube video or playlist HTTP(S) link")
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query)
    parts = parsed.path.strip("/").split("/")
    video_id = ""
    if parsed.hostname == "youtu.be" and len(parts) == 1:
        video_id = parts[0]
    elif parts == ["watch"]:
        video_id = query.get("v", [""])[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
        video_id = parts[1]
    list_id = query.get("list", [""])[0]
    if video_id and not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
        raise ValueError("The video identifier is invalid")
    if list_id and not re.fullmatch(r"[a-zA-Z0-9_-]+", list_id):
        raise ValueError("The playlist identifier is invalid")
    if not video_id and not (parts == ["playlist"] and list_id):
        raise ValueError("This link does not identify a supported video or playlist")
    return YouTubeInput(
        kind="ambiguous" if video_id and list_id else "video" if video_id else "playlist",
        video_url="https://www.youtube.com/watch?v=" + video_id if video_id else "",
        playlist_url="https://www.youtube.com/playlist?list=" + list_id if list_id else "",
    )


@dataclass
class TextImport:
    links: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)


def parse_text_links(text: str) -> TextImport:
    result = TextImport()
    seen: dict[str, int] = {}
    for number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "]")):
            continue
        try:
            source = classify_url(line)
            if source.kind != "video":
                raise ValueError("TXT imports accept individual video links only")
        except ValueError as exc:
            result.issues.append(f"Line {number}: {exc}: {line}")
            continue
        if source.video_url in seen:
            result.duplicates.append(f"Line {number}: same video as line {seen[source.video_url]}")
        else:
            seen[source.video_url] = number
            result.links.append(source.video_url)
    return result
