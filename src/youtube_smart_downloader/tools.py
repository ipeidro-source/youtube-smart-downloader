"""Local tool validation and conservative, scoped winget maintenance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Literal

from .processes import Cancelled, ProcessRunner
from .settings import config_file
from .storage import atomic_text


@dataclass(frozen=True)
class ToolSpec:
    name: str
    package: str
    description: str
    version_pattern: str


SPECS = (
    ToolSpec(
        "yt-dlp", "yt-dlp.yt-dlp", "YouTube metadata and downloads", r"^(\d{4}\.\d{2}\.\d{2}\S*)"
    ),
    ToolSpec(
        "ffmpeg", "yt-dlp.FFmpeg", "Video/audio merging and conversion", r"^ffmpeg version (\S+)"
    ),
    ToolSpec(
        "ffprobe",
        "yt-dlp.FFmpeg",
        "Downloaded media validation (included with FFmpeg)",
        r"^ffprobe version (\S+)",
    ),
    ToolSpec(
        "deno", "DenoLand.Deno", "JavaScript runtime used by yt-dlp", r"^deno (\d+\.\d+\.\d+\S*)"
    ),
)


def windows_supported() -> bool:
    return os.name == "nt"


@dataclass(frozen=True)
class ToolStatus:
    spec: ToolSpec
    path: str = ""
    version: str = ""
    error: str = ""
    update: Literal["unknown", "current", "available"] = "unknown"
    available_version: str = ""
    update_message: str = "Not checked"

    @property
    def usable(self) -> bool:
        return bool(self.path and self.version and not self.error)


def parse_winget_row(output: str, package: str) -> tuple[str, str | None] | None:
    """Read only exact package rows; headers and other localized prose are irrelevant."""
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output).replace("\r", "\n")
    for line in output.splitlines():
        match = re.search(rf"(?<!\S){re.escape(package)}\s+(.+?)\s*$", line)
        if match:
            columns = match.group(1).split()
            # --source winget can hide the Source column entirely.
            if columns[-1] == "winget":
                columns.pop()
            if len(columns) in {1, 2} and all(re.search(r"\d", value) for value in columns):
                return columns[0], columns[1] if len(columns) == 2 else None
    return None


def winget_managed(status: ToolStatus) -> bool:
    try:
        path = Path(status.path).resolve().as_posix().lower()
    except OSError:
        return False
    return f"/winget/packages/{status.spec.package.lower()}_" in path


class ToolManager:
    CACHE_SECONDS = 6 * 60 * 60

    def __init__(self, cancel_event: threading.Event, cache_path: Path | None = None) -> None:
        self.runner = ProcessRunner(cancel_event)
        self.cache_path = cache_path or config_file().with_name("tool-updates.json")

    def impersonation_targets(self) -> list[str]:
        """Only advertise installed browser families; probing never needs the network."""
        try:
            output = self.runner.run(
                ["yt-dlp", "--ignore-config", "--list-impersonate-targets"],
                capture_all=True,
                timeout=10,
            )
        except (OSError, RuntimeError, ValueError, TimeoutError):
            return []
        return parse_impersonation_targets(output)

    def probe(self) -> list[ToolStatus]:
        result = []
        for spec in SPECS:
            self.runner.check_cancelled()
            path = shutil.which(spec.name)
            if not path:
                result.append(ToolStatus(spec, error="Not found on PATH"))
                continue
            try:
                flag = "-version" if spec.name in {"ffmpeg", "ffprobe"} else "--version"
                output = self.runner.run([path, flag], capture_all=True, timeout=5)
                match = re.search(spec.version_pattern, output, re.M)
                if not match:
                    raise ValueError("Unrecognized version output")
                result.append(ToolStatus(spec, path=path, version=match.group(1)))
            except Cancelled:
                raise
            except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                result.append(ToolStatus(spec, path=path, error=str(exc)))
        return result

    def check_updates(self, statuses: list[ToolStatus]) -> list[ToolStatus]:
        self.runner.check_cancelled()
        statuses = [
            replace(s, update="unknown", available_version="", update_message="Not checked")
            for s in statuses
        ]
        if not windows_supported() or not shutil.which("winget"):
            return [
                replace(s, update_message="Update status unknown: winget is unavailable")
                for s in statuses
            ]
        fingerprint = hashlib.sha256(
            json.dumps([(s.spec.name, s.path, s.version, s.error) for s in statuses]).encode()
        ).hexdigest()
        try:
            cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if (
                cache["fingerprint"] == fingerprint
                and 0 <= time.time() - cache["time"] < self.CACHE_SECONDS
            ):
                rows = cache["rows"]
                if isinstance(rows, dict):
                    result = []
                    for status in statuses:
                        row = rows[status.spec.name]
                        if row["update"] not in {"current", "available", "unknown"}:
                            raise ValueError("Invalid cache")
                        if not all(
                            isinstance(row[k], str)
                            for k in ("update", "available_version", "update_message")
                        ):
                            raise ValueError("Invalid cache")
                        result.append(
                            replace(
                                status,
                                update=row["update"],
                                available_version=row["available_version"],
                                update_message=row["update_message"],
                            )
                        )
                    return result
        except (OSError, ValueError, KeyError, TypeError):
            pass
        packages: dict[str, tuple[str, str | None] | None] = {}
        result = []
        for status in statuses:
            self.runner.check_cancelled()
            if not status.usable or not winget_managed(status):
                result.append(
                    replace(
                        status,
                        update_message="Update status unknown: executable is not a recognized winget portable installation",
                    )
                )
                continue
            package = status.spec.package
            if package not in packages:
                try:
                    output = self.runner.run(
                        [
                            "winget",
                            "list",
                            "--id",
                            package,
                            "--exact",
                            "--source",
                            "winget",
                            "--accept-source-agreements",
                            "--disable-interactivity",
                        ],
                        capture_all=True,
                        timeout=12,
                    )
                    packages[package] = parse_winget_row(output, package)
                except Cancelled:
                    raise
                except (OSError, RuntimeError, TimeoutError):
                    packages[package] = None
            row = packages[package]
            if row is None:
                result.append(
                    replace(
                        status,
                        update_message="Update status unknown: package query failed or returned unrecognized data",
                    )
                )
            elif row[1] is not None:
                result.append(
                    replace(
                        status,
                        update="available",
                        available_version=row[1],
                        update_message=f"Update available: {row[1]} (winget)",
                    )
                )
            else:
                result.append(
                    replace(
                        status, update="current", update_message="Up to date in the winget catalog"
                    )
                )
        # Cache only successful catalog results. Network failures are retried next startup.
        if all(s.update != "unknown" for s in result if s.usable):
            try:
                atomic_text(
                    self.cache_path,
                    json.dumps(
                        {
                            "time": time.time(),
                            "fingerprint": fingerprint,
                            "rows": {
                                s.spec.name: {
                                    "update": s.update,
                                    "available_version": s.available_version,
                                    "update_message": s.update_message,
                                }
                                for s in result
                            },
                        }
                    ),
                )
            except OSError:
                pass
        return result

    def maintain(
        self, statuses: list[ToolStatus], log: Callable[[str], None], *, update: bool
    ) -> None:
        if not windows_supported() or not shutil.which("winget"):
            raise RuntimeError(
                "Automatic maintenance requires Windows and winget. Install the listed tools manually and restart the app."
            )
        packages = (
            {s.spec.package for s in statuses if s.update == "available" and s.usable}
            if update
            else {s.spec.package for s in statuses if not s.usable}
        )
        for package in sorted(packages):
            self.runner.check_cancelled()
            operation = "upgrade" if update else "install"
            log(f"{operation.capitalize()}: {package}")
            command = [
                "winget",
                operation,
                "--id",
                package,
                "--exact",
                "--source",
                "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity",
            ]
            if not update and any(s.spec.package == package and s.path for s in statuses):
                command.append("--force")
            self.runner.run(command, on_line=lambda line: log(line[-1300:]) if line else None)
        self.runner.check_cancelled()
        try:
            self.cache_path.unlink(missing_ok=True)
        except OSError as exc:
            log(f"Could not clear the update cache: {exc}")
        log("Maintenance finished. Restart the app if PATH has changed.")


def parse_impersonation_targets(output: str) -> list[str]:
    families = set()
    for line in output.splitlines():
        columns = line.split()
        if len(columns) == 3 and columns[2] == "curl_cffi":
            client = columns[0].lower().split("-", 1)[0]
            if re.fullmatch(r"[a-z]+", client):
                families.add(client)
    return sorted(families)
