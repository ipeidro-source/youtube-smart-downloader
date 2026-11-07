"""Local user preferences; no credentials are persisted."""

import json
import os
from pathlib import Path
from typing import Any

from .core import LANGUAGES, QUALITY
from .storage import atomic_text


def config_file() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return base / "YouTubeSmartDownloader" / "settings.json"


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Use the same validated values internally and in the visible controls."""
    result = dict(data)
    for key, values, default in (
        ("language", LANGUAGES, "es"),
        ("quality", QUALITY, "best"),
        ("mode", {"video": None, "playlist": None}, "playlist"),
        ("missing", {"skip": None, "fallback": None}, "skip"),
    ):
        if not isinstance(result.get(key), str) or result[key] not in values:
            result[key] = default
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
