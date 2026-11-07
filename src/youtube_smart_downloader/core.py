"""Pure download planning and language-selection helpers.

No network calls or GUI imports live here, making the risky decisions testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


LANGUAGES = {
    "es-ES": "Español (España)",
    "es-419": "Español (Latinoamérica)",
    "es": "Español (cualquier variante)",
    "en": "Inglés",
    "original": "Original / predeterminado",
    "auto": "Automático",
}
QUALITY = {"best": None, "1080": 1080, "720": 720, "480": 480}


@dataclass(frozen=True)
class Preferences:
    language: str = "es"
    missing: str = "skip"  # skip or fallback
    quality: str = "best"
    playlist_subfolder: bool = True

    def validate(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError("Idioma desconocido")
        if self.missing not in {"skip", "fallback"}:
            raise ValueError("Política de idioma desconocida")
        if self.quality not in QUALITY:
            raise ValueError("Calidad desconocida")


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
            domain in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
        )
    except ValueError:
        return False


def safe_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return name[:100] or "Lista de reproducción"


def select_video(formats: list[dict], quality: str) -> str | None:
    ceiling = QUALITY[quality]
    options = [
        f for f in formats
        if f.get("vcodec") not in {None, "none"}
        and f.get("acodec") == "none"
        and f.get("format_id")
        and (ceiling is None or (f.get("height") or 0) <= ceiling)
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
    if requested == "es":
        return actual == "es" or actual.startswith("es-")
    if requested == "es-ES":
        return actual in {"es-es", "es"}  # generic Spanish is not proof of region
    if requested == "es-419":
        return actual == "es-419" or actual.startswith("es-419-")
    return actual == requested or actual.startswith(requested + "-")


def select_audio(formats: list[dict], language: str) -> AudioChoice:
    """Select ONE audio-only format. No silent fallback for a specified language.

    Generic 'es' cannot establish Spain vs LatAm; reject it for the Spain-specific
    selection unless no region is requested. Missing language metadata is not proof.
    """
    tracks = [
        f for f in formats
        if f.get("acodec") not in {None, "none"}
        and f.get("vcodec") == "none"
        and f.get("format_id")
    ]
    if not tracks:
        return AudioChoice(None, "?", "Sin pistas de audio independientes", False)

    if language not in {"auto", "original"}:
        if language == "es-ES":
            choices = [f for f in tracks if normalize_language(f.get("language")) == "es-es"]
        else:
            choices = [
                f for f in tracks if language_matches(str(f.get("language") or ""), language)
            ]
        if not choices:
            return AudioChoice(None, "?", "Idioma solicitado no identificado", False)
        choices.sort(key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0))
        selected = choices[-1]
        return AudioChoice(str(selected["format_id"]), str(selected.get("language")), "Coincidencia etiquetada", True)

    # Original: yt-dlp marks original tracks through format_note on some extractors.
    # If that evidence is absent, use the extractor's default preference only.
    if language == "original":
        original = [f for f in tracks if "original" in str(f.get("format_note", "")).lower()]
        if original:
            tracks = original
        else:
            defaults = [f for f in tracks if f.get("language_preference", -1) >= 0]
            if defaults:
                tracks = defaults
    tracks.sort(key=lambda f: (f.get("language_preference") or -1, f.get("abr") or 0, f.get("tbr") or 0))
    selected = tracks[-1]
    return AudioChoice(
        str(selected["format_id"]), str(selected.get("language") or "desconocido"),
        "Audio original confirmado" if language == "original" and "original" in str(selected.get("format_note", "")).lower() else "Preferencia del extractor (no verificada)",
        False,
    )


def output_template(index: int | None = None) -> str:
    prefix = f"{index:03d} - " if index is not None else ""
    return prefix + "%(title).180B [%(id)s].%(ext)s"


def download_args(url: str, directory: Path, video_id: str | None, audio_id: str | None,
                  quality: str, index: int | None) -> list[str]:
    """Explicit formats prevent accidentally choosing a different language."""
    fmt = f"{video_id}+{audio_id}" if video_id and audio_id else (audio_id or "best")
    if quality not in QUALITY:
        raise ValueError("Calidad desconocida")
    return [
        "--no-playlist", "--newline", "--continue", "--no-overwrites", "--ignore-errors",
        "--windows-filenames", "--download-archive", str(directory / ".ytsd-archive.txt"),
        "-P", str(directory), "-o", output_template(index),
        "-f", fmt, "--merge-output-format", "mp4", "--recode-video", "mp4",
        "--progress-template", "download:%(progress._percent_str)s", url,
    ]
