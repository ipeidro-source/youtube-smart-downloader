"""Pure download planning and language-selection helpers.

No network calls or GUI imports live here, making the risky decisions testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from .requests import TimeRange


LANGUAGES = {
    "es-ES": "Spanish (Spain)",
    "es-419": "Spanish (Latin America)",
    "es": "Spanish (any region)",
    "en": "English",
    "original": "Original / default",
    "auto": "Automatic",
}
QUALITY = {"best": None, "1080": 1080, "720": 720, "480": 480}


def describe_format(track: dict[str, Any], *, audio: bool) -> dict[str, Any]:
    """Keep technical metadata and add a description without guessing from format IDs."""
    codec = str(track.get("acodec" if audio else "vcodec") or "unknown")
    names = {
        "avc1": "H.264",
        "h264": "H.264",
        "av01": "AV1",
        "vp09": "VP9",
        "vp9": "VP9",
        "hvc1": "H.265",
        "hev1": "H.265",
        "hevc": "H.265",
        "mp4a": "AAC",
        "aac": "AAC",
        "opus": "Opus",
        "vorbis": "Vorbis",
    }
    friendly = next(
        (value for key, value in names.items() if codec.lower().split(".")[0] == key), codec
    )
    details = {
        "id": str(track.get("format_id") or "unknown"),
        "codec": codec,
        "codec_name": friendly,
        "container": track.get("ext"),
        "bitrate_kbps": track.get("abr" if audio else "tbr"),
    }
    if audio:
        language = str(track.get("language") or "unknown")
        label = LANGUAGES.get(language, language)
        channels = track.get("audio_channels")
        details.update(language=language, channels=channels)
        parts = [
            label,
            friendly,
            f"{details['bitrate_kbps']} kbps"
            if details["bitrate_kbps"] is not None
            else "Unknown bitrate",
            f"{channels} channels" if channels is not None else "Unknown channels",
        ]
    else:
        width, height, fps = track.get("width"), track.get("height"), track.get("fps")
        details.update(width=width, height=height, fps=fps)
        resolution = (
            f"{width}x{height}"
            if width and height
            else f"{height}p"
            if height
            else "Unknown resolution"
        )
        parts = [resolution, f"{fps} fps" if fps is not None else "Unknown frame rate", friendly]
    details["description"] = " | ".join(parts)
    return details


@dataclass(frozen=True)
class Preferences:
    language: str = "es"
    missing: str = "skip"  # skip or fallback
    quality: str = "best"
    playlist_subfolder: bool = True  # Legacy settings key; applies to every input type.

    def validate(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError("Unknown audio language")
        if self.missing not in {"skip", "fallback"}:
            raise ValueError("Unknown missing-language policy")
        if self.quality not in QUALITY:
            raise ValueError("Unknown quality")


@dataclass(frozen=True)
class AudioChoice:
    format_id: str | None
    detected_language: str
    reason: str
    verified: bool


def valid_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        domain = (parsed.hostname or "").lower()
        return parsed.scheme in {"https", "http"} and (
            domain
            in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
        )
    except ValueError:
        return False


def safe_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    name = name[:100].rstrip(" .") or "Playlist"
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name, re.I):
        name = "_" + name
    return name


def select_video(formats: list[dict[str, Any]], quality: str) -> str | None:
    ceiling = QUALITY[quality]
    options = [
        f
        for f in formats
        if f.get("vcodec") not in {None, "none"}
        and f.get("acodec") == "none"
        and f.get("format_id")
        and (ceiling is None or (f.get("height") is not None and f["height"] <= ceiling))
    ]
    if not options:
        return None
    options.sort(key=lambda f: (f.get("height") or 0, f.get("fps") or 0, f.get("tbr") or 0))
    return str(options[-1]["format_id"])


def normalize_language(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("_", "-")


def language_matches(actual: str, requested: str) -> bool:
    actual = normalize_language(actual)
    requested = normalize_language(requested)
    if requested == "es":
        return actual == "es" or actual.startswith("es-")
    if requested == "es-es":
        return actual == "es-es"
    if requested == "es-419":
        return actual == "es-419" or actual.startswith("es-419-")
    return actual == requested or actual.startswith(requested + "-")


def _original_track(track: dict[str, Any]) -> bool:
    # Do not treat notes such as "not original" or "originality" as evidence.
    return (
        bool(
            re.search(
                r"(?:^|[,;\s])\(original\)(?:$|[,;\s])", str(track.get("format_note", "")), re.I
            )
        )
        or str(track.get("format_note", "")).strip().lower() == "original"
    )


def select_audio(formats: list[dict[str, Any]], language: str) -> AudioChoice:
    """Select ONE audio-only format. No silent fallback for a specified language.

    Generic 'es' cannot establish Spain vs LatAm; reject it for the Spain-specific
    selection unless no region is requested. Missing language metadata is not proof.
    """
    tracks = [
        f
        for f in formats
        if f.get("acodec") not in {None, "none"}
        and f.get("vcodec") == "none"
        and f.get("format_id")
    ]
    if not tracks:
        return AudioChoice(None, "?", "No independent audio tracks", False)

    if language not in {"auto", "original"}:
        choices = [f for f in tracks if language_matches(str(f.get("language") or ""), language)]
        if not choices:
            return AudioChoice(None, "?", "Requested audio language not identified", False)
        choices.sort(key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0))
        selected = choices[-1]
        return AudioChoice(
            str(selected["format_id"]),
            str(selected.get("language")),
            "Language matched by metadata",
            True,
        )

    # Original: yt-dlp marks original tracks through format_note on some extractors.
    # If that evidence is absent, use the extractor's default preference only.
    if language == "original":
        original = [f for f in tracks if _original_track(f)]
        if original:
            tracks = original
        else:
            defaults = [
                f
                for f in tracks
                if f.get("language_preference") is not None and f["language_preference"] >= 0
            ]
            if defaults:
                tracks = defaults
    tracks.sort(
        key=lambda f: (
            f["language_preference"] if f.get("language_preference") is not None else -1,
            f.get("abr") or 0,
            f.get("tbr") or 0,
        )
    )
    selected = tracks[-1]
    return AudioChoice(
        str(selected["format_id"]),
        str(selected.get("language") or "unknown"),
        "Track marked as original by the extractor"
        if language == "original" and _original_track(selected)
        else "Extractor preference (unverified)",
        language == "original" and _original_track(selected),
    )


def output_template(index: int | None = None) -> str:
    prefix = f"{index:03d} - " if index is not None else ""
    return prefix + "%(title).180B [%(id)s].%(ext)s"


def download_args(
    url: str,
    directory: Path,
    video_id: str,
    audio_id: str,
    quality: str,
    index: int | None,
    *,
    info_file: Path | None = None,
    time_range: TimeRange | None = None,
) -> list[str]:
    """Explicit formats prevent accidentally choosing a different language."""
    if not video_id or not audio_id:
        raise ValueError("Independent video and audio tracks are required")
    fmt = f"{video_id}+{audio_id}"
    if quality not in QUALITY:
        raise ValueError("Unknown quality")
    return [
        "--no-playlist",
        *(["--download-sections", "*" + time_range.key] if time_range else []),
        "--newline",
        "--continue",
        "--no-overwrites",
        "--abort-on-error",
        "--windows-filenames",
        "--keep-video",
        "-P",
        str(directory),
        "-o",
        "%(id)s.%(ext)s",
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        "--recode-video",
        "mp4",
        "--progress-template",
        "download:YTSD_PROGRESS:%(progress._percent_str)s",
        *(["--load-info-json", str(info_file)] if info_file is not None else [url]),
    ]
