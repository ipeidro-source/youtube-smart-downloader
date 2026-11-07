"""Local user preferences; no credentials are persisted."""

import json
import os
from pathlib import Path


def config_file() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return base / "YouTubeSmartDownloader" / "settings.json"


def load() -> dict:
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(settings: dict) -> None:
    destination = config_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)
