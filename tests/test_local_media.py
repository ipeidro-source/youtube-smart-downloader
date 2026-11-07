"""Offline integration: real yt-dlp + FFmpeg + ffprobe, synthetic media over loopback."""

import functools
import json
import re
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest

from youtube_smart_downloader.core import Preferences
from youtube_smart_downloader.engine import Cancelled, DownloadEngine


pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("yt-dlp", "ffmpeg", "ffprobe")),
    reason="Requires external tools; tests never install tools or query YouTube",
)
URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def media(tmp_path):
    def ffmpeg(arguments):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", *arguments], check=True, capture_output=True, timeout=30
        )

    ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=24",
            "-t",
            "3",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(tmp_path / "video.mp4"),
        ]
    )
    for language, frequency in (("es", "440"), ("en", "880")):
        ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}",
                "-t",
                "3",
                "-c:a",
                "aac",
                str(tmp_path / f"{language}.m4a"),
            ]
        )

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            path = tmp_path / self.path.lstrip("/")
            if path.name not in {"video.mp4", "es.m4a", "en.m4a"} or path.parent != tmp_path:
                self.send_error(404)
                return
            match = re.fullmatch(r"bytes=(\d+)-", self.headers.get("Range", ""))
            start = int(match.group(1)) if match else 0
            requests.append((path.name, start))
            size = path.stat().st_size
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(size - start))
            self.send_header("Accept-Ranges", "bytes")
            if start:
                self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
            self.end_headers()
            with path.open("rb") as stream:
                stream.seek(start)
                try:
                    shutil.copyfileobj(stream, self.wfile)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        def log_message(self, *args):
            pass

    requests = []
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(tmp_path))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    info = {
        "id": "abcdefghijk",
        "title": "Local sample",
        "duration": 3,
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": URL,
        "formats": [
            {
                "format_id": "v",
                "url": base + "/video.mp4",
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 180,
                "protocol": "http",
            },
            *[
                {
                    "format_id": lang,
                    "url": base + f"/{lang}.m4a",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a",
                    "language": lang,
                    "abr": 128,
                    "protocol": "http",
                }
                for lang in ("es", "en")
            ],
        ],
    }
    info_path = tmp_path / "fixture.info.json"
    info_path.write_text(json.dumps(info), encoding="utf-8")
    try:
        yield info, info_path, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def local_engine(monkeypatch, media, *, progress=None, rate_limit=False):
    info, _info_path, _requests = media
    engine = DownloadEngine(Mock(), progress or Mock())
    monkeypatch.setattr(engine, "missing_tools", lambda: [])
    monkeypatch.setattr(engine, "_metadata", lambda *args, **kwargs: info)
    if rate_limit:
        original_run = engine._run

        def run(arguments, **kwargs):
            return original_run(["--limit-rate", "300K", *arguments], **kwargs)

        monkeypatch.setattr(engine, "_run", run)
    return engine


def test_real_local_download_selects_only_requested_audio(monkeypatch, media, tmp_path):
    engine = local_engine(monkeypatch, media)
    destination = tmp_path / "output"
    report = engine.download(URL, destination, False, Preferences(language="es"))
    assert report["downloaded"], report
    assert Path(report["directory"]) == destination / "Local sample"
    assert report["items"][0]["audio_format"] == "es"
    output = Path(report["items"][0]["output"])
    engine._verify_media(output, 3)

    # Decode and compare the actual audio to the requested synthetic Spanish source.
    def pcm(path):
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-"],
            check=True,
            capture_output=True,
            timeout=15,
        ).stdout

    assert pcm(output) == pcm(tmp_path / "es.m4a")
    assert pcm(output) != pcm(tmp_path / "en.m4a")
    assert not list((Path(report["directory"]) / ".ytsd-work").iterdir())
    again = local_engine(monkeypatch, media).download(URL, destination, False, Preferences())
    assert len(again["archived"]) == 1 and not again["downloaded"]


def test_real_cancellation_then_retry(monkeypatch, media, tmp_path):
    engine = local_engine(monkeypatch, media, rate_limit=True)

    def cancel_after_data(_number, _total, percentage):
        if float(percentage.rstrip("%")) >= 30 and any(
            path.stat().st_size > 0
            for path in (destination / "Local sample/.ytsd-work").glob("*/*.part")
        ):
            engine.cancel()

    engine.progress = cancel_after_data
    destination = tmp_path / "output"
    with pytest.raises(Cancelled):
        engine.download(URL, destination, False, Preferences())
    assert any(
        path.stat().st_size > 0
        for path in (destination / "Local sample/.ytsd-work").glob("*/*.part")
    )
    assert not (destination / "Local sample/.ytsd-archive.txt").exists()
    report = local_engine(monkeypatch, media).download(URL, destination, False, Preferences())
    assert report["downloaded"], report
    assert Path(report["items"][0]["output"]).is_file()
    assert any(start > 0 for _name, start in media[2]), "yt-dlp must request the remaining bytes"


def test_probe_rejects_audio_only_output(monkeypatch, media, tmp_path):
    engine = DownloadEngine(Mock(), Mock())
    with pytest.raises(RuntimeError, match="exactly one"):
        engine._verify_media(tmp_path / "es.m4a", 3)
