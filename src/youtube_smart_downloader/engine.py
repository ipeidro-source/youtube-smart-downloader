"""Subprocess wrapper around installed yt-dlp, FFmpeg and Deno executables."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from .core import Preferences, download_args, safe_name, select_audio, select_video


class Cancelled(Exception):
    """Raised when a user cancels a running job."""


class DownloadEngine:
    def __init__(self, status: Callable[[str], None], progress: Callable[[int, int, str], None]):
        self.status = status
        self.progress = progress
        self.cancel_event = threading.Event()
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @staticmethod
    def missing_tools() -> list[str]:
        return [tool for tool in ("yt-dlp", "ffmpeg", "deno") if not shutil.which(tool)]

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            process = self._process
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                               capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                process.terminate()

    def _run(self, arguments: list[str], *, json_output: bool = False,
             current: int = 0, total: int = 1) -> str:
        if self.cancel_event.is_set():
            raise Cancelled
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        command = ["yt-dlp", "--no-warnings", *arguments]
        with self._lock:
            self._process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", encoding="utf-8", creationflags=flags,
            )
            process = self._process
        lines = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if self.cancel_event.is_set():
                    raise Cancelled
                line = line.strip()
                lines.append(line)
                if not json_output and line:
                    match = re.search(r"download:\s*([\d.]+)%", line)
                    if match:
                        self.progress(current, total, match.group(1) + "%")
                    elif line.startswith("ERROR:"):
                        self.status(line[:240])
            rc = process.wait()
            if self.cancel_event.is_set():
                raise Cancelled
            if rc:
                raise RuntimeError("yt-dlp terminó con error: " + " ".join(lines[-5:])[-500:])
            return "\n".join(lines)
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()

    def _metadata(self, url: str, flat: bool = False) -> dict:
        args = ["--dump-single-json", "--skip-download", "--flat-playlist" if flat else "--no-playlist", url]
        data = self._run(args, json_output=True)
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise RuntimeError("No se ha podido interpretar la información del vídeo") from exc

    @staticmethod
    def _video_url(entry: dict) -> str:
        url = str(entry.get("url") or "")
        if url.startswith("https://") or url.startswith("http://"):
            return url
        vid = str(entry.get("id") or url)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", vid):
            raise ValueError("Entrada de lista sin enlace válido")
        return "https://www.youtube.com/watch?v=" + vid

    def download(self, url: str, directory: Path, playlist: bool, prefs: Preferences) -> dict:
        prefs.validate()
        self.cancel_event.clear()
        if self.missing_tools():
            raise RuntimeError("Faltan herramientas: " + ", ".join(self.missing_tools()))
        directory.mkdir(parents=True, exist_ok=True)
        if playlist:
            self.status("Leyendo lista de reproducción…")
            listing = self._metadata(url, flat=True)
            entries = listing.get("entries") or []
            if not entries:
                raise RuntimeError("La lista está vacía o no está disponible")
            if prefs.playlist_subfolder:
                directory = directory / safe_name(str(listing.get("title") or "Lista de reproducción"))
                directory.mkdir(parents=True, exist_ok=True)
            videos = [(self._video_url(e), i) for i, e in enumerate(entries, 1) if e]
        else:
            videos = [(url, None)]
        report = {"downloaded": [], "omitted": [], "failed": [], "directory": str(directory)}
        for number, (video_url, index) in enumerate(videos, 1):
            if self.cancel_event.is_set():
                raise Cancelled
            self.status(f"Analizando vídeo {number} de {len(videos)}…")
            try:
                metadata = self._metadata(video_url)
                title = str(metadata.get("title") or video_url)
                formats = metadata.get("formats") or []
                choice = select_audio(formats, prefs.language)
                if choice.format_id is None and prefs.missing == "fallback":
                    choice = select_audio(formats, "original")
                if choice.format_id is None:
                    report["omitted"].append(f"{title}: {choice.reason}")
                    self.status(f"Omitido: {title} (sin pista solicitada)")
                    continue
                video_id = select_video(formats, prefs.quality)
                if not video_id:
                    # Some videos offer combined A/V only; choosing them could change
                    # the language, so never silently substitute that stream.
                    report["omitted"].append(f"{title}: vídeo independiente no disponible")
                    continue
                self.status(f"Descargando: {title} — audio {choice.detected_language} ({choice.reason})")
                self._run(download_args(video_url, directory, video_id, choice.format_id,
                                        prefs.quality, index), current=number, total=len(videos))
                report["downloaded"].append(f"{title}: {choice.detected_language} ({choice.reason})")
            except Cancelled:
                raise
            except Exception as exc:  # keep processing remaining playlist entries
                report["failed"].append(f"{video_url}: {exc}")
                self.status(f"Error en vídeo {number}: {exc}")
            self.progress(number, len(videos), "100%")
        report_path = directory / "informe-descarga.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report


def install_missing(log: Callable[[str], None]) -> None:
    if os.name != "nt" or not shutil.which("winget"):
        raise RuntimeError("Instalación automática disponible solo en Windows con winget")
    # Make an explicit attempt for all three components, even when yt-dlp is
    # already installed but FFmpeg or Deno are missing.
    packages = [
        ("yt-dlp", "yt-dlp.yt-dlp"),
        ("ffmpeg", "yt-dlp.FFmpeg"),
        ("deno", "DenoLand.Deno"),
    ]
    flags = subprocess.CREATE_NO_WINDOW
    for executable, package in packages:
        if shutil.which(executable):
            continue
        log(f"Instalando {package}…")
        proc = subprocess.run(
            ["winget", "install", "--id", package, "-e", "--accept-package-agreements",
             "--accept-source-agreements"], text=True, capture_output=True, errors="replace",
            creationflags=flags, check=False,
        )
        log((proc.stdout + "\n" + proc.stderr)[-1300:])
        if proc.returncode:
            raise RuntimeError(f"winget no pudo instalar {package}; comprueba el mensaje anterior")
    log("Instalación finalizada. Reinicia la aplicación para actualizar el PATH.")
