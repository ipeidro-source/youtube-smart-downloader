"""Atomic local files and structured download reports."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypedDict


class DownloadReport(TypedDict):
    schema_version: int
    downloaded: list[str]
    archived: list[str]
    omitted: list[str]
    failed: list[str]
    items: list[dict[str, Any]]
    directory: str
    state: str
    report_path: str
    error: str


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_report(report: DownloadReport) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False)
    atomic_text(Path(report["report_path"]), text)
    root = Path(report["report_path"]).parents[1]
    if root != Path(report["directory"]):
        atomic_text(root / "download-report.json", text)
    atomic_text(Path(report["directory"]) / "download-report.json", text)


def publish_file(source: Path, destination: Path) -> None:
    """Publish on the same volume, atomically, without overwriting an existing file."""
    if os.name == "nt":
        source.rename(destination)
    else:
        os.link(source, destination)
        source.unlink()


def read_archive(directory: Path) -> set[str]:
    try:
        return set((directory / ".ytsd-archive.txt").read_text(encoding="utf-8").splitlines())
    except FileNotFoundError:
        return set()


def archive_video(directory: Path, video_id: str) -> None:
    archive = read_archive(directory)
    archive.add("youtube " + video_id)
    atomic_text(directory / ".ytsd-archive.txt", "\n".join(sorted(archive)) + "\n")
