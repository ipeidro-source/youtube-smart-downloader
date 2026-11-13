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
    resolve_tracks,
    TrackPlan,
    select_video,
    valid_youtube_url,
)
from .processes import Cancelled as Cancelled
from .inputs import classify_url
from .requests import DownloadRequest, TimeRange
from .processes import ProcessRunner
from .subtitles import clip_subrip
from .languages import container_language
from .tools import ToolManager
from .storage import (
    DownloadReport,
    archive_video,
    archive_clip,
    clip_key,
    read_clip_archive,
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
        self.impersonation = "auto"

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
            [
                "yt-dlp",
                "--ignore-config",
                "--encoding",
                "utf-8",
                *(["--impersonate", self.impersonation] if self.impersonation != "auto" else []),
                *arguments,
            ],
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

    def _verify_media(
        self,
        path: Path,
        expected_duration: float | None,
        *,
        clip: bool = False,
        plan: TrackPlan | None = None,
    ) -> None:
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError("No final media file was produced")
        output = self.runner.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_all=True,
        )
        data = json.loads(output)
        kinds = [stream.get("codec_type") for stream in data.get("streams", [])]
        container = data.get("format", {})
        duration = float(container.get("duration") or 0)
        if (
            kinds.count("video") != 1
            or kinds.count("audio") != (len(plan.audios) if plan else 1)
            or duration <= 0
        ):
            expected_audio = len(plan.audios) if plan else 1
            raise RuntimeError(
                f"The final file must contain one video and exactly {expected_audio} valid audio track(s), with positive duration"
            )
        expected_container = "matroska" if plan and plan.container == "mkv" else "mp4"
        if expected_container not in str(container.get("format_name", "")).split(","):
            raise RuntimeError("The final file has the wrong container")
        if plan:
            streams = data.get("streams", [])
            audio = [x for x in streams if x.get("codec_type") == "audio"]
            subs = [x for x in streams if x.get("codec_type") == "subtitle"]
            if len(subs) != len(plan.subtitles):
                raise RuntimeError("Missing embedded subtitle tracks")
            for stream, language in zip(
                audio + subs,
                [a.detected_language for a in plan.audios]
                + [x["language"] for x in plan.subtitles],
            ):
                tags = stream.get("tags", {})
                if tags.get("language", "und") != container_language(language):
                    raise RuntimeError("Incorrect container language tag")
                if language not in (tags.get("title"), tags.get("handler_name")):
                    raise RuntimeError("Incorrect track language metadata")
            if [i for i, x in enumerate(audio) if x.get("disposition", {}).get("default")] != [
                plan.default_index
            ]:
                raise RuntimeError("Incorrect default audio track")
            # MP4 uses the enabled flag for subtitle availability, not automatic rendering.
            # FFmpeg enables the first subtitle even when disposition is explicitly zero.
            if any(x.get("disposition", {}).get("forced") for x in subs) or (
                plan.container == "mkv"
                and any(x.get("disposition", {}).get("default") for x in subs)
            ):
                raise RuntimeError("Subtitles must be disabled by default")
        if expected_duration and duration < expected_duration - max(2, expected_duration * 0.05):
            raise RuntimeError("The final file appears incomplete (shorter than expected)")
        if (
            clip
            and expected_duration
            and duration > expected_duration + max(2, expected_duration * 0.05)
        ):
            raise RuntimeError("The final fragment is longer than expected")

    def _download_one(
        self,
        video_url: str,
        index: int | None,
        directory: Path,
        prefs: Preferences,
        report: DownloadReport,
        number: int,
        total: int,
        time_range: TimeRange | None = None,
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
        if time_range:
            item["time_range"] = {"start": time_range.start, "end": time_range.end}
            title += f" [{time_range.key}s]"
        raw_duration = metadata.get("duration")
        duration = float(raw_duration) if isinstance(raw_duration, (int, float)) else None
        if time_range:
            duration = time_range.duration(duration)
        archived = (
            clip_key(video_id, time_range) in read_clip_archive(directory)
            if time_range
            else "youtube " + video_id in read_archive(directory)
        )
        if archived:
            item.update(status="archived", reason="Already recorded in this folder's archive")
            report["archived"].append(title)
            self.status(f"Already archived: {title} (track selection and format are not rechecked)")
            return
        formats = metadata.get("formats") or []
        plan = resolve_tracks(metadata, prefs)
        # Retain resumable work paths for callers of the original single-language API.
        # The UI always supplies explicit audio lists.
        explicit_tracks = (
            prefs.audio_languages is not None
            or bool(prefs.subtitle_languages)
            or prefs.container != "mp4"
        )
        choice = plan.audios[0] if plan.audios else select_audio([], prefs.language)
        fallback = plan.fallback
        original = select_audio(formats, "original")
        item.update(
            requested_language=prefs.requested_audio[0],
            requested_audio=list(prefs.requested_audio),
            requested_subtitles=list(prefs.subtitle_languages),
            missing_audio=list(plan.missing_audio),
            missing_subtitles=list(plan.missing_subtitles),
            included_audio=[
                dict(
                    format_id=a.format_id,
                    language=a.detected_language,
                    reason=a.reason,
                    verified=a.verified,
                )
                for a in plan.audios
            ],
            included_subtitles=[{k: x[k] for k in ("language", "source")} for x in plan.subtitles],
            default_audio_index=plan.default_index,
            original_audio={"language": original.detected_language, "verified": original.verified},
            container=plan.container,
            audio_language=choice.detected_language,
            verified=choice.verified and not fallback,
            fallback=fallback,
            reason=choice.reason,
        )
        self.status(
            f"Original/default audio: {original.detected_language} ({'verified' if original.verified else 'unverified extractor preference'})"
        )
        for label, missing in (
            ("audio", plan.missing_audio),
            ("subtitles", plan.missing_subtitles),
        ):
            if missing:
                self.status(f"WARNING: {title}: unavailable {label}: {', '.join(missing)}")
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
        selected_audio = next(f for f in formats if f.get("format_id") == choice.format_id)
        selected_video = next(f for f in formats if f.get("format_id") == video_format)
        item.update(
            video_details=describe_format(selected_video, audio=False),
            audio_details=describe_format(selected_audio, audio=True),
            audio_tracks=[
                describe_format(
                    next(f for f in formats if f.get("format_id") == a.format_id), audio=True
                )
                for a in plan.audios
            ],
        )
        identity = {
            key: selected_audio.get(key)
            for key in ("format_id", "language", "format_note", "acodec", "asr", "audio_channels")
        }
        if explicit_tracks:
            identity = {
                "audios": [
                    {
                        key: next(f for f in formats if f.get("format_id") == a.format_id).get(key)
                        for key in (
                            "format_id",
                            "language",
                            "format_note",
                            "acodec",
                            "asr",
                            "audio_channels",
                        )
                    }
                    for a in plan.audios
                ],
                "subtitles": [(x["language"], x["source"]) for x in plan.subtitles],
                "container": plan.container,
                "default": plan.default_index,
            }
        profile = hashlib.sha256(
            json.dumps(
                [video_format, identity, time_range.key]
                if time_range
                else [video_format, identity],
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12]
        workdir = directory / ".ytsd-work" / f"{video_id}-{profile}"
        workdir.mkdir(parents=True, exist_ok=True)
        staged = workdir / (
            f"{video_id}.final.{plan.container}" if explicit_tracks else f"{video_id}.mp4"
        )
        verification: dict[str, Any] = {"plan": plan} if explicit_tracks else {}
        if time_range:
            verification["clip"] = True
        ready = False
        if staged.exists():
            try:
                self._verify_media(staged, duration, **verification)
                ready = True
            except Cancelled:
                raise
            except (RuntimeError, ValueError):
                # Only remove the invalid generated output in our private workdir.
                staged.unlink()
        self.status(
            f"Downloading: {title} | audio {', '.join(a.detected_language for a in plan.audios)}; {plan.container.upper()}"
        )
        for subtitle in plan.subtitles:
            self.status(
                f"Subtitles: {subtitle['language']} ({'automatic' if subtitle['source'] == 'automatic_captions' else 'published'})"
            )
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
                f
                for f in formats
                if f.get("format_id") in {video_format, *(a.format_id for a in plan.audios)}
            ]
            info_file = workdir / "source.info.json"
            atomic_text(info_file, json.dumps(snapshot, ensure_ascii=False))
            args = download_args(
                video_url,
                workdir,
                video_format,
                choice.format_id,
                prefs.quality,
                index,
                info_file=info_file,
                time_range=time_range,
                audio_ids=tuple(str(a.format_id) for a in plan.audios),
                container="mkv" if explicit_tracks else "mp4",
                copy_streams=explicit_tracks,
            )
            self._run(args, current=number, total=total)
            if explicit_tracks:
                self._assemble(snapshot, workdir, video_id, staged, plan, time_range, duration)
        self._verify_media(staged, duration, **verification)
        self.runner.check_cancelled()
        prefix = f"{index:03d} - " if index is not None else ""
        destination = directory / f"{prefix}{safe_name(title)} [{video_id}].{plan.container}"
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
        if time_range:
            archive_clip(directory, video_id, time_range)
        else:
            archive_video(directory, video_id)
        report["downloaded"].append(
            f"{title}: {', '.join(a.detected_language for a in plan.audios)} ({plan.container.upper()})"
        )
        try:
            shutil.rmtree(workdir)
        except OSError as exc:
            self.status(f"Download complete; could not clean temporary files: {exc}")

    def _assemble(
        self,
        metadata: dict[str, Any],
        workdir: Path,
        video_id: str,
        staged: Path,
        plan: TrackPlan,
        time_range: TimeRange | None,
        duration: float | None,
    ) -> None:
        subtitle_files = []
        for index, subtitle in enumerate(plan.subtitles):
            snapshot = dict(metadata)
            snapshot["subtitles"] = {subtitle["language"]: subtitle["formats"]}
            snapshot["automatic_captions"] = {}
            info = workdir / f"subtitle-{index}.info.json"
            atomic_text(info, json.dumps(snapshot, ensure_ascii=False))
            self._run(
                [
                    "--load-info-json",
                    str(info),
                    "--skip-download",
                    "--write-subs",
                    "--sub-langs",
                    subtitle["language"],
                    "--sub-format",
                    "srt/vtt/ttml/best",
                    "--convert-subs",
                    "srt",
                    "-P",
                    str(workdir),
                    "-o",
                    f"subtitle-{index}.%(ext)s",
                ]
            )
            path = workdir / f"subtitle-{index}.{subtitle['language']}.srt"
            if not path.is_file():
                raise RuntimeError(f"Subtitle download failed: {subtitle['language']}")
            if time_range:
                clipped = workdir / f"subtitle-{index}.clip.srt"
                atomic_text(
                    clipped,
                    clip_subrip(
                        path.read_text(encoding="utf-8-sig"),
                        time_range.start,
                        time_range.start + duration if duration else None,
                    ),
                )
                path = clipped
            subtitle_files.append(path)
        command = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-i",
            str(workdir / f"{video_id}.mkv"),
        ]
        for path in subtitle_files:
            command += ["-f", "srt", "-i", str(path)]
        command += ["-map", "0:v:0"]
        for index in range(len(plan.audios)):
            command += ["-map", f"0:a:{index}"]
        for index in range(len(subtitle_files)):
            command += ["-map", f"{index + 1}:s:0"]
        command += ["-c", "copy", "-map_metadata", "-1"]
        if plan.container == "mp4":
            formats = metadata.get("formats") or []
            video = next(
                f
                for f in formats
                if f.get("vcodec") not in {None, "none"} and f.get("acodec") == "none"
            )
            if str(video.get("vcodec", "")).split(".")[0] not in {
                "avc1",
                "h264",
                "av01",
                "av1",
                "hvc1",
                "hev1",
                "hevc",
                "vp09",
                "vp9",
            }:
                command += ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]
            for index, choice in enumerate(plan.audios):
                audio = next(f for f in formats if f.get("format_id") == choice.format_id)
                if str(audio.get("acodec", "")).split(".")[0] not in {
                    "mp4a",
                    "aac",
                    "opus",
                    "mp3",
                    "ac3",
                    "eac3",
                    "alac",
                }:
                    command += [f"-c:a:{index}", "aac", f"-b:a:{index}", "192k"]
        if subtitle_files:
            command += ["-c:s", "srt" if plan.container == "mkv" else "mov_text"]
        for kind, languages in (
            ("a", [a.detected_language for a in plan.audios]),
            ("s", [x["language"] for x in plan.subtitles]),
        ):
            for index, language in enumerate(languages):
                # Preserve the full regional tag in title; ISO 639-2 in language for players.
                iso = container_language(language)
                command += [
                    f"-metadata:s:{kind}:{index}",
                    f"language={iso}",
                    f"-metadata:s:{kind}:{index}",
                    f"title={language}",
                    f"-metadata:s:{kind}:{index}",
                    f"handler_name={language}",
                    f"-disposition:{kind}:{index}",
                    "default" if kind == "a" and index == plan.default_index else "0",
                ]
        if time_range and duration:
            command += ["-t", str(duration)]
        command += [str(staged)]
        self.runner.run(command)

    def download(
        self,
        url: str | DownloadRequest | list[str] | list[DownloadRequest],
        directory: Path,
        playlist: bool,
        prefs: Preferences,
        *,
        batch_name: str | None = None,
    ) -> DownloadReport:
        prefs.validate()
        self.impersonation = prefs.impersonation
        single_range = None
        if isinstance(url, DownloadRequest):
            single_range = url.time_range
            if playlist and single_range:
                raise ValueError("Playlists do not support time ranges")
            url = url.url
        requests: list[DownloadRequest] = []
        if isinstance(url, list):
            if playlist or not url:
                raise ValueError("A batch must contain individual video links")
            for link in url:
                request = link if isinstance(link, DownloadRequest) else DownloadRequest(link)
                if classify_url(request.url).kind != "video":
                    raise ValueError("A batch must contain individual video links")
                requests.append(request)
        elif not valid_youtube_url(url):
            raise ValueError("Enter a valid YouTube HTTP(S) link")
        directory.mkdir(parents=True, exist_ok=True)
        session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        report: DownloadReport = {
            "schema_version": 3,
            "impersonation": prefs.impersonation,
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
            if prefs.impersonation != "auto":
                targets = ToolManager(self.cancel_event).impersonation_targets()
                if prefs.impersonation not in targets:
                    raise ValueError(
                        "Impersonation profile unavailable. Choose Automatic or update yt-dlp."
                    )
            videos: list[tuple[Any, int | None]]
            if isinstance(url, list):
                directory = self._source_directory(
                    directory, batch_name or "Imported videos", prefs, report
                )
                videos = [
                    ({"url": request.url, "time_range": request.time_range}, i)
                    for i, request in enumerate(requests, 1)
                ]
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
                videos = [({"url": url, "time_range": single_range}, None)]
            for number, (entry, index) in enumerate(videos, 1):
                self.runner.check_cancelled()
                video_url = f"Entry {number}"
                first_item = len(report["items"])
                self.status(f"Analyzing video {number} of {len(videos)}…")
                time_range = (
                    entry.get("time_range") if isinstance(entry, dict) and not playlist else None
                )
                try:
                    video_url = self._video_url(entry)
                    self._download_one(
                        video_url,
                        index,
                        directory,
                        prefs,
                        report,
                        number,
                        len(videos),
                        time_range=time_range,
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
                        failed_item: dict[str, Any] = {
                            "url": video_url,
                            "status": "failed",
                            "error": str(exc),
                        }
                        if time_range:
                            failed_item["time_range"] = {
                                "start": time_range.start,
                                "end": time_range.end,
                            }
                        report["items"].append(failed_item)
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
