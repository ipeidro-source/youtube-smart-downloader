"""Local user preferences; no credentials are persisted."""

import json
import os
from pathlib import Path
from typing import Any

from .core import LANGUAGES, QUALITY, valid_language, normalize_language, valid_impersonation
from .storage import atomic_text


def config_file() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return base / "YouTubeSmartDownloader" / "settings.json"


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Use the same validated values internally and in the visible controls."""
    result = dict(data)
    result.pop("mode", None)  # Input type is inferred from the URL, not a saved UI mode.
    for key, values, default in (
        ("language", LANGUAGES, "es-ES"),
        ("quality", QUALITY, "best"),
        ("missing", {"skip": None, "fallback": None}, "skip"),
    ):
        if not isinstance(result.get(key), str) or result[key] not in values:
            result[key] = default
    # Adopt the new Spanish/English defaults for the old Spanish-only setup.
    # Explicit multi-track selections and other legacy languages remain unchanged.
    audio_default = ["es-ES", "en"]
    legacy_language = data.get("language")
    if (
        isinstance(legacy_language, str)
        and legacy_language in LANGUAGES
        and legacy_language not in {"es", "es-ES"}
    ):
        audio_default = [legacy_language]
    for key, language_default, audio in (
        ("audio_languages", audio_default, True),
        ("subtitle_languages", ["es", "en"], False),
    ):
        language_values = result.get(key)
        if not isinstance(language_values, list):
            language_values = language_default
        seen: set[str] = set()
        result[key] = []
        for value in language_values:
            normalized = normalize_language(value)
            if valid_language(value, audio=audio) and normalized not in seen:
                result[key].append(value)
                seen.add(normalized)
        if audio and not result[key]:
            result[key] = language_default
    if result.get("default_audio") not in result["audio_languages"]:
        result["default_audio"] = result["audio_languages"][0]
    if result.get("container") not in ("mp4", "mkv"):
        result["container"] = "mkv"
    if not valid_impersonation(result.get("impersonation")):
        result["impersonation"] = "auto"
    if not isinstance(result.get("automatic_subtitles"), bool):
        result["automatic_subtitles"] = False
    if not isinstance(result.get("playlist_subfolder"), bool):
        result["playlist_subfolder"] = True
    if not isinstance(result.get("destination"), str) or not result["destination"].strip():
        result["destination"] = str(Path.home() / "Downloads")
    return result


def load() -> dict[str, Any]:
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
        return normalize(data if isinstance(data, dict) else {})
    except (OSError, ValueError):
        return normalize({})


def save(settings: dict[str, Any]) -> None:
    destination = config_file()
    atomic_text(destination, json.dumps(normalize(settings), ensure_ascii=False, indent=2))
