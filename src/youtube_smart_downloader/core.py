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

    audio_languages: tuple[str, ...] | None = None
    subtitle_languages: tuple[str, ...] = ()
    default_audio: str | None = None
    automatic_subtitles: bool = False
    container: str = "mkv"
    impersonation: str = "auto"

    @property
    def requested_audio(self) -> tuple[str, ...]:
        return self.audio_languages if self.audio_languages is not None else (self.language,)

    def validate(self) -> None:
        if not valid_impersonation(self.impersonation):
            raise ValueError("Invalid impersonation profile")
        if not self.requested_audio or any(
            not valid_language(x, audio=True) for x in self.requested_audio
        ):
            raise ValueError("Choose at least one valid audio language")
        if any(not valid_language(x) for x in self.subtitle_languages):
            raise ValueError("Invalid subtitle language")
        if self.default_audio and self.default_audio not in self.requested_audio:
            raise ValueError("Default audio must be among requested languages")
        if self.container not in {"mp4", "mkv"}:
            raise ValueError("Unknown container")
        if self.audio_languages is None and self.language not in LANGUAGES:
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
    audio_ids: tuple[str, ...] | None = None,
    container: str = "mkv",
    copy_streams: bool = False,
) -> list[str]:
    """Explicit formats prevent accidentally choosing a different language."""
    if not video_id or not audio_id:
        raise ValueError("Independent video and audio tracks are required")
    selected_audio = audio_ids if audio_ids is not None else (audio_id,)
    if not selected_audio or any(not track for track in selected_audio):
        raise ValueError("At least one audio track is required")
    if container not in {"mp4", "mkv"}:
        raise ValueError("Unknown container")
    fmt = "+".join((video_id, *selected_audio))
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
        *(["--audio-multistreams"] if len(selected_audio) > 1 else []),
        "--merge-output-format",
        container,
        *([] if copy_streams else ["--recode-video", container]),
        "--progress-template",
        "download:YTSD_PROGRESS:%(progress._percent_str)s",
        *(["--load-info-json", str(info_file)] if info_file is not None else [url]),
    ]


def valid_language(value: object, *, audio: bool = False) -> bool:
    return isinstance(value, str) and (
        (audio and value in {"original", "auto"})
        or (
            value not in {"original", "auto", "live_chat"}
            and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value) is not None
        )
    )


@dataclass(frozen=True)
class TrackPlan:
    audios: tuple[AudioChoice, ...]
    subtitles: tuple[dict[str, Any], ...]
    missing_audio: tuple[str, ...]
    missing_subtitles: tuple[str, ...]
    default_index: int
    container: str
    fallback: bool


def resolve_tracks(metadata: dict[str, Any], prefs: Preferences) -> TrackPlan:
    audios: list[AudioChoice] = []
    indices: dict[str, int] = {}
    missing: list[str] = []
    for language in prefs.requested_audio:
        choice = select_audio(metadata.get("formats") or [], language)
        if not choice.format_id:
            missing.append(language)
            continue
        existing = next((i for i, a in enumerate(audios) if a.format_id == choice.format_id), None)
        indices[language] = len(audios) if existing is None else existing
        if existing is None:
            audios.append(choice)
    fallback = not audios and prefs.missing == "fallback"
    if fallback:
        choice = select_audio(metadata.get("formats") or [], "original")
        if choice.format_id:
            audios.append(choice)
    subtitles: list[dict[str, Any]] = []
    absent: list[str] = []
    for requested in prefs.subtitle_languages:
        selected = None
        for source in (
            ("subtitles", "automatic_captions") if prefs.automatic_subtitles else ("subtitles",)
        ):
            candidates = metadata.get(source) or {}
            keys = sorted(
                k for k in candidates if valid_language(k) and language_matches(k, requested)
            )
            keys.sort(key=lambda k: normalize_language(k) != normalize_language(requested))
            for key in keys:
                formats = [
                    f
                    for f in candidates[key]
                    if f.get("url") and f.get("ext") in {"srt", "vtt", "ttml", "srv3", "json3"}
                ]
                if formats:
                    selected = {"language": key, "source": source, "formats": formats}
                    break
            if selected:
                break
        if selected:
            if not any(s["language"] == selected["language"] for s in subtitles):
                subtitles.append(selected)
        else:
            absent.append(requested)
    return TrackPlan(
        tuple(audios),
        tuple(subtitles),
        tuple(missing),
        tuple(absent),
        indices.get(prefs.default_audio or prefs.requested_audio[0], 0),
        prefs.container,
        fallback,
    )


def valid_impersonation(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 80
        and (value == "auto" or re.fullmatch(r"[a-z][a-z0-9-]*(?::[a-z0-9-]+)?", value) is not None)
    )
