"""Download orchestration; processes and atomic persistence live in separate modules."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .core import (
    Preferences,
    download_args,
    describe_format,
    safe_name,
    select_audio,
    select_video,
    valid_youtube_url,
)
from .processes import Cancelled as Cancelled
from .inputs import classify_url
from .processes import ProcessRunner
from .storage import (
    DownloadReport,
    archive_video,
    atomic_text,
    publish_file,
    read_archive,
    write_report,
)


class DownloadEngine:
    """One engine per job. A cancelled engine is never reset or reused."""

    def __init__(self, status: Callable[[str], None], progress: Callable[[int, int, str], None]):
        self.status = status
        self.progress = progress
        self.cancel_event = threading.Event()
        self.runner = ProcessRunner(self.cancel_event)
        self.report: DownloadReport | None = None

    @staticmethod
    def missing_tools() -> list[str]:
        return [tool for tool in ("yt-dlp", "ffmpeg", "ffprobe", "deno") if not shutil.which(tool)]

    def cancel(self) -> None:
        self.cancel_event.set()

    @staticmethod
    def _source_directory(
        directory: Path, name: str, prefs: Preferences, report: DownloadReport
    ) -> Path:
        if prefs.playlist_subfolder:
            directory = directory / safe_name(name)
            directory.mkdir(parents=True, exist_ok=True)
        report["directory"] = str(directory)
        return directory

    def _run(
        self, arguments: list[str], *, json_output: bool = False, current: int = 0, total: int = 1
    ) -> str:
        def on_line(line: str) -> None:
            match = re.search(r"^YTSD_PROGRESS:\s*([\d.]+)%$", line)
            if match:
                self.progress(current, total, match.group(1) + "%")
            elif line.startswith(("ERROR:", "WARNING:", "[Merger]", "[VideoConvertor]")):
                self.status(line[:500])

        return self.runner.run(
            ["yt-dlp", "--ignore-config", "--encoding", "utf-8", *arguments],
            capture_all=json_output,
            on_line=None if json_output else on_line,
        )

    def _metadata(self, url: str, flat: bool = False) -> dict[str, Any]:
        args = [
            "--dump-single-json",
            "--skip-download",
            "--flat-playlist" if flat else "--no-playlist",
            url,
        ]
        data = self._run(args, json_output=True)
        try:
            # stderr shares the pipe; warnings may surround the single JSON line.
            for line in reversed(data.splitlines()):
                if line.startswith("{"):
                    result = json.loads(line)
                    if isinstance(result, dict):
                        return result
        except json.JSONDecodeError as exc:
            raise RuntimeError("Could not parse video metadata") from exc
        raise RuntimeError("yt-dlp returned no valid metadata")

    @staticmethod
    def _video_url(entry: Any) -> str:
        if not isinstance(entry, dict):
            raise ValueError("Unavailable playlist entry")
        url = str(entry.get("url") or "")
        if valid_youtube_url(url):
            return url
        vid = str(entry.get("id") or url)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", vid):
            raise ValueError("Playlist entry has no valid link")
        return "https://www.youtube.com/watch?v=" + vid

    def _verify_media(self, path: Path, expected_duration: float | None) -> None:
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError("No final MP4 was produced")
        output = self.runner.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_all=True,
        )
        data = json.loads(output)
        kinds = [stream.get("codec_type") for stream in data.get("streams", [])]
        container = data.get("format", {})
        duration = float(container.get("duration") or 0)
        if kinds.count("video") != 1 or kinds.count("audio") != 1 or duration <= 0:
            raise RuntimeError(
                "The final file must contain one video and exactly one valid audio track"
            )
        if "mp4" not in str(container.get("format_name", "")).split(","):
            raise RuntimeError("The final file is not an MP4 container")
        if expected_duration and duration < expected_duration - max(2, expected_duration * 0.05):
            raise RuntimeError("The final file appears incomplete (shorter than expected)")

    def _download_one(
        self,
        video_url: str,
        index: int | None,
        directory: Path,
        prefs: Preferences,
        report: DownloadReport,
        number: int,
        total: int,
    ) -> None:
        metadata = self._metadata(video_url)
        video_id = str(metadata.get("id") or "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
            raise ValueError("Invalid video identifier")
        title = str(metadata.get("title") or video_id)
        if index is None:
            directory = self._source_directory(directory, title, prefs, report)
        item: dict[str, Any] = {"url": video_url, "id": video_id, "title": title}
        report["items"].append(item)
        if "youtube " + video_id in read_archive(directory):
            item.update(status="archived", reason="Already recorded in this folder's archive")
            report["archived"].append(title)
            self.status(f"Already archived: {title} (audio language is not rechecked)")
            return
        formats = metadata.get("formats") or []
        choice = select_audio(formats, prefs.language)
        fallback = choice.format_id is None and prefs.missing == "fallback"
        if fallback:
            choice = select_audio(formats, "original")
        item.update(
            requested_language=prefs.language,
            audio_language=choice.detected_language,
            verified=choice.verified and not fallback,
            fallback=fallback,
            reason=choice.reason,
        )
        video_format = select_video(formats, prefs.quality)
        if not choice.format_id or not video_format:
            reason = (
                choice.reason
                if not choice.format_id
                else "No independent video stream available at this quality"
            )
            item.update(status="omitted", reason=reason)
            report["omitted"].append(f"{title}: {reason}")
            self.status(f"Skipped: {title} ({reason})")
            return
        if metadata.get("is_live"):
            raise ValueError("Wait for the live stream to finish before downloading")
        raw_duration = metadata.get("duration")
        duration = float(raw_duration) if isinstance(raw_duration, (int, float)) else None
        selected_audio = next(f for f in formats if f.get("format_id") == choice.format_id)
        selected_video = next(f for f in formats if f.get("format_id") == video_format)
        item.update(
            video_details=describe_format(selected_video, audio=False),
            audio_details=describe_format(selected_audio, audio=True),
        )
        identity = {
            key: selected_audio.get(key)
            for key in ("format_id", "language", "format_note", "acodec", "asr", "audio_channels")
        }
        profile = hashlib.sha256(
            json.dumps([video_format, identity], sort_keys=True).encode()
        ).hexdigest()[:12]
        workdir = directory / ".ytsd-work" / f"{video_id}-{profile}"
        workdir.mkdir(parents=True, exist_ok=True)
        staged = workdir / f"{video_id}.mp4"
        ready = False
        if staged.exists():
            try:
                self._verify_media(staged, duration)
                ready = True
            except Cancelled:
                raise
            except (RuntimeError, ValueError):
                # Only remove the invalid generated output in our private workdir.
                staged.unlink()
        self.status(f"Downloading: {title} — audio {choice.detected_language} ({choice.reason})")
        if not ready:
            # Download exactly the metadata whose language we inspected, without a second
            # extraction that could assign different suffixes to multilingual format IDs.
            snapshot = {
                key: value
                for key, value in metadata.items()
                if key
                not in {
                    "requested_downloads",
                    "requested_formats",
                    "_filename",
                    "filename",
                    "filepath",
                }
            }
            snapshot["formats"] = [
                f for f in formats if f.get("format_id") in {video_format, choice.format_id}
            ]
            info_file = workdir / "source.info.json"
            atomic_text(info_file, json.dumps(snapshot, ensure_ascii=False))
            self._run(
                download_args(
                    video_url,
                    workdir,
                    video_format,
                    choice.format_id,
                    prefs.quality,
                    index,
                    info_file=info_file,
                ),
                current=number,
                total=total,
            )
        self._verify_media(staged, duration)
        self.runner.check_cancelled()
        prefix = f"{index:03d} - " if index is not None else ""
        destination = directory / f"{prefix}{safe_name(title)} [{video_id}].mp4"
        if destination.exists():
            raise FileExistsError(
                f"{destination.name} already exists; review or move it before retrying"
            )
        publish_file(staged, destination)
        item.update(
            status="downloaded",
            output=str(destination),
            video_format=video_format,
            audio_format=choice.format_id,
        )
        archive_video(directory, video_id)
        report["downloaded"].append(f"{title}: {choice.detected_language} ({choice.reason})")
        try:
            shutil.rmtree(workdir)
        except OSError as exc:
            self.status(f"Download complete; could not clean temporary files: {exc}")

    def download(
        self,
        url: str | list[str],
        directory: Path,
        playlist: bool,
        prefs: Preferences,
        *,
        batch_name: str | None = None,
    ) -> DownloadReport:
        prefs.validate()
        if isinstance(url, list):
            if playlist or not url:
                raise ValueError("A batch must contain individual video links")
            for link in url:
                if classify_url(link).kind != "video":
                    raise ValueError("A batch must contain individual video links")
        elif not valid_youtube_url(url):
            raise ValueError("Enter a valid YouTube HTTP(S) link")
        directory.mkdir(parents=True, exist_ok=True)
        session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        report: DownloadReport = {
            "schema_version": 2,
            "downloaded": [],
            "archived": [],
            "omitted": [],
            "failed": [],
            "items": [],
            "directory": str(directory),
            "state": "running",
            "error": "",
            "report_path": str(directory / ".ytsd-reports" / f"{session}.json"),
        }
        self.report = report
        try:
            write_report(report)
            self.runner.check_cancelled()
            missing = self.missing_tools()
            if missing:
                raise RuntimeError("Missing tools: " + ", ".join(missing))
            videos: list[tuple[Any, int | None]]
            if isinstance(url, list):
                directory = self._source_directory(
                    directory, batch_name or "Imported videos", prefs, report
                )
                videos = [({"url": link}, i) for i, link in enumerate(url, 1)]
            elif playlist:
                self.status("Reading playlist…")
                listing = self._metadata(url, flat=True)
                entries = listing.get("entries") or []
                directory = self._source_directory(
                    directory, str(listing.get("title") or "Playlist"), prefs, report
                )
                if not entries:
                    raise RuntimeError("The playlist is empty or unavailable")
                videos = [(entry, i) for i, entry in enumerate(entries, 1)]
            else:
                videos = [({"url": url}, None)]
            for number, (entry, index) in enumerate(videos, 1):
                self.runner.check_cancelled()
                video_url = f"Entry {number}"
                first_item = len(report["items"])
                self.status(f"Analyzing video {number} of {len(videos)}…")
                try:
                    video_url = self._video_url(entry)
                    self._download_one(
                        video_url, index, directory, prefs, report, number, len(videos)
                    )
                except Cancelled:
                    if len(report["items"]) > first_item:
                        report["items"][-1]["status"] = "cancelled"
                    raise
                except Exception as exc:
                    report["failed"].append(f"{video_url}: {exc}")
                    if len(report["items"]) > first_item:
                        report["items"][-1].update(status="failed", error=str(exc))
                    else:
                        report["items"].append(
                            {"url": video_url, "status": "failed", "error": str(exc)}
                        )
                    self.status(f"Video {number} failed: {exc}")
                finally:
                    write_report(report)
                self.progress(number, len(videos), "100%")
            self.runner.check_cancelled()
            report["state"] = "completed_with_errors" if report["failed"] else "completed"
            return report
        except Cancelled:
            report["state"] = "cancelled"
            raise
        except Exception as exc:
            report["state"] = "failed"
            report["error"] = str(exc)
            raise
        finally:
            write_report(report)
