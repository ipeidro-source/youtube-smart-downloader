"""Offline integration: real yt-dlp + FFmpeg + ffprobe, synthetic media over loopback."""

import functools
from array import array
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
from youtube_smart_downloader.requests import DownloadRequest, TimeRange


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
            "-g",
            "12",
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

    for language in ("es", "en"):
        (tmp_path / f"{language}.srt").write_text(
            "1\n00:00:00,100 --> 00:00:00,500\nBEFORE\n\n"
            "2\n00:00:00,500 --> 00:00:01,500\nCROSSING\n\n"
            "3\n00:00:01,500 --> 00:00:01,800\n" + language + " INSIDE\n\n"
            "4\n00:00:02,500 --> 00:00:02,900\nAFTER\n",
            encoding="utf-8",
        )

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            path = tmp_path / self.path.lstrip("/")
            if (
                path.name not in {"video.mp4", "es.m4a", "en.m4a", "es.srt", "en.srt"}
                or path.parent != tmp_path
            ):
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
    report = engine.download(URL, destination, False, Preferences(container="mp4", language="es"))
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
    again = local_engine(monkeypatch, media).download(
        URL,
        destination,
        False,
        Preferences(
            container="mp4",
        ),
    )
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
        engine.download(
            URL,
            destination,
            False,
            Preferences(
                container="mp4",
            ),
        )
    assert any(
        path.stat().st_size > 0
        for path in (destination / "Local sample/.ytsd-work").glob("*/*.part")
    )
    assert not (destination / "Local sample/.ytsd-archive.txt").exists()
    report = local_engine(monkeypatch, media).download(
        URL,
        destination,
        False,
        Preferences(
            container="mp4",
        ),
    )
    assert report["downloaded"], report
    assert Path(report["items"][0]["output"]).is_file()
    assert any(start > 0 for _name, start in media[2]), "yt-dlp must request the remaining bytes"


def test_probe_rejects_audio_only_output(monkeypatch, media, tmp_path):
    engine = DownloadEngine(Mock(), Mock())
    with pytest.raises(RuntimeError, match="exactly 1"):
        engine._verify_media(tmp_path / "es.m4a", 3)


@pytest.mark.parametrize("time_range", [TimeRange(1, 2), TimeRange(1), TimeRange(0, 2)])
def test_real_local_time_ranges(monkeypatch, media, tmp_path, time_range):
    engine = local_engine(monkeypatch, media)
    report = engine.download(
        DownloadRequest(URL, time_range),
        tmp_path / "clips",
        False,
        Preferences(container="mp4", language="es"),
    )
    assert report["downloaded"], report
    item = report["items"][0]
    assert item["audio_format"] == "es"
    output = Path(item["output"])
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)],
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout
    )
    assert abs(float(probe["format"]["duration"]) - time_range.duration(3)) < 0.6
    assert sorted(s["codec_type"] for s in probe["streams"]) == ["audio", "video"]
    # Decode the actual output to catch malformed packets or an unplayable cut.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
        check=True,
        capture_output=True,
        timeout=15,
    )
    pcm = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(output),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout
    samples = array("h", pcm)
    crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
    frequency = crossings / (len(samples) / 8000)
    assert 430 < frequency < 450, "The clip must contain Spanish 440Hz, not English 880Hz"
    assert not (Path(report["directory"]) / ".ytsd-archive.txt").exists()


def add_subtitles(media):
    info = media[0]
    base = info["formats"][0]["url"].rsplit("/", 1)[0]
    info["subtitles"] = {
        lang: [{"url": base + f"/{lang}.srt", "ext": "srt"}] for lang in ("es", "en")
    }


def probe(path):
    return json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            timeout=15,
        ).stdout
    )


@pytest.mark.parametrize(
    "languages,preferred,extension",
    [
        (("es", "en"), "mp4", "mp4"),
        (("es", "en"), "mkv", "mkv"),
        (("es",), "mp4", "mp4"),
        (("es", "fr"), "mp4", "mp4"),
        (("es",), "mkv", "mkv"),
    ],
)
def test_real_embedded_tracks(monkeypatch, media, tmp_path, languages, preferred, extension):
    add_subtitles(media)
    engine = local_engine(monkeypatch, media)
    prefs = Preferences(
        audio_languages=languages,
        subtitle_languages=("es", "en", "fr"),
        default_audio=languages[-1],
        container=preferred,
    )
    report = engine.download(URL, tmp_path / "result", False, prefs)
    assert report["downloaded"], report
    item = report["items"][0]
    output = Path(item["output"])
    assert output.suffix == "." + extension
    streams = probe(output)["streams"]
    audio = [x for x in streams if x["codec_type"] == "audio"]
    subs = [x for x in streams if x["codec_type"] == "subtitle"]
    assert len(audio) == (2 if "en" in languages else 1)
    assert len(subs) == 2
    assert [i for i, x in enumerate(audio) if x["disposition"]["default"]] == [
        1 if "en" in languages else 0
    ]
    assert not any(x["disposition"]["forced"] for x in subs)
    if extension == "mkv":
        assert not any(x["disposition"]["default"] for x in subs)
    assert [x["tags"]["language"] for x in audio] == (
        ["spa", "eng"] if "en" in languages else ["spa"]
    )
    assert item["missing_subtitles"] == ["fr"]
    if "fr" in languages:
        assert item["missing_audio"] == ["fr"]
    # Compare decoded audio, allowing the container's final packet padding.
    for index, language in enumerate(("es", "en")[: len(audio)]):

        def pcm(path, mapping):
            return subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(path), "-map", mapping, "-f", "s16le", "-"],
                check=True,
                capture_output=True,
                timeout=15,
            ).stdout

        actual = pcm(output, f"0:a:{index}")
        expected = pcm(tmp_path / f"{language}.m4a", "0:a:0")
        # Remuxing AAC through Matroska can change priming/padding metadata.
        # Compare the signal itself, independently of those boundary samples.
        for decoded in (actual, expected):
            samples = array("h", decoded)[22050:110250]
            frequency = sum(a <= 0 < b for a, b in zip(samples, samples[1:])) / (
                len(samples) / 44100
            )
            assert abs(frequency - (440 if language == "es" else 880)) < 2
    for index, language in enumerate(("es", "en")):
        text = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(output), "-map", f"0:s:{index}", "-f", "srt", "-"],
            check=True,
            capture_output=True,
            timeout=15,
        ).stdout.decode()
        assert language + " INSIDE" in text
    assert not list(Path(report["directory"]).glob("*.srt"))
    assert not list((Path(report["directory"]) / ".ytsd-work").iterdir())
    repeated = engine.download(
        URL, tmp_path / "result", False, Preferences(audio_languages=("en",))
    )
    assert repeated["archived"]


@pytest.mark.parametrize("container", ["mp4", "mkv"])
def test_real_clip_embedded_subtitle_timing(monkeypatch, media, tmp_path, container):
    add_subtitles(media)
    engine = local_engine(monkeypatch, media)
    prefs = Preferences(
        audio_languages=("es", "en"),
        subtitle_languages=("es",),
        container=container,
    )
    report = engine.download(DownloadRequest(URL, TimeRange(1, 2)), tmp_path / "clip", False, prefs)
    assert report["downloaded"], report
    output = report["items"][0]["output"]
    text = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", output, "-map", "0:s:0", "-f", "srt", "-"],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout.decode()
    assert "BEFORE" not in text and "AFTER" not in text
    assert "CROSSING" in text and "es INSIDE" in text
    assert "00:00:00,500 --> 00:00:00,800" in text
    assert abs(float(probe(output)["format"]["duration"]) - 1) < 0.2


@pytest.mark.parametrize("container", ["mp4", "mkv"])
def test_real_clip_without_subtitle_cues(monkeypatch, media, tmp_path, container):
    add_subtitles(media)
    # No cues overlap this interval.
    (tmp_path / "es.srt").write_text("1\n00:00:00,100 --> 00:00:00,500\nBEFORE\n", encoding="utf-8")
    report = local_engine(monkeypatch, media).download(
        DownloadRequest(URL, TimeRange(2, 3)),
        tmp_path / "empty",
        False,
        Preferences(audio_languages=("es",), subtitle_languages=("es",), container=container),
    )
    assert report["downloaded"], report["failed"]


def test_real_subtitle_failure_retains_work_and_retry_uses_it(monkeypatch, media, tmp_path):
    add_subtitles(media)
    original_url = media[0]["subtitles"]["es"][0]["url"]
    media[0]["subtitles"]["es"][0]["url"] = original_url.replace("es.srt", "missing.srt")
    prefs = Preferences(audio_languages=("es", "en"), subtitle_languages=("es",))
    destination = tmp_path / "retry"
    report = local_engine(monkeypatch, media).download(URL, destination, False, prefs)
    assert report["failed"] and not report["downloaded"]
    folder = Path(report["directory"])
    assert not (folder / ".ytsd-archive.txt").exists()
    assert not list(folder.glob("*.mkv"))
    assert list((folder / ".ytsd-work").glob("*/*.mkv"))
    video_requests = sum(name == "video.mp4" for name, _ in media[2])
    media[0]["subtitles"]["es"][0]["url"] = original_url
    report = local_engine(monkeypatch, media).download(URL, destination, False, prefs)
    assert report["downloaded"], report["failed"]
    assert sum(name == "video.mp4" for name, _ in media[2]) == video_requests


def test_real_cancel_before_assembly_then_retry(monkeypatch, media, tmp_path):
    add_subtitles(media)
    engine = local_engine(monkeypatch, media)
    run = engine.runner.run

    def cancel_assembly(command, **kwargs):
        if command[0] == "ffmpeg":
            engine.cancel()
        return run(command, **kwargs)

    monkeypatch.setattr(engine.runner, "run", cancel_assembly)
    destination = tmp_path / "cancel-multiple"
    prefs = Preferences(audio_languages=("es", "en"), subtitle_languages=("es",))
    with pytest.raises(Cancelled):
        engine.download(URL, destination, False, prefs)
    assert engine.report["state"] == "cancelled"
    assert not list(destination.rglob(".ytsd-archive.txt"))
    assert list(destination.rglob("*.mkv"))
    video_requests = sum(name == "video.mp4" for name, _ in media[2])
    report = local_engine(monkeypatch, media).download(URL, destination, False, prefs)
    assert report["downloaded"], report["failed"]
    assert sum(name == "video.mp4" for name, _ in media[2]) == video_requests


@pytest.mark.parametrize("languages", [("es",), ("en", "es")])
def test_real_mp4_converts_incompatible_codecs(monkeypatch, media, tmp_path, languages):
    # Serve WebM/Ogg content through the existing fixture URLs.
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x120:rate=24",
            "-t",
            "3",
            "-c:v",
            "libvpx",
            "-f",
            "webm",
            str(tmp_path / "video.mp4"),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "3",
            "-c:a",
            "libvorbis",
            "-f",
            "ogg",
            str(tmp_path / "es.m4a"),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    media[0]["formats"][0].update(vcodec="vp8", ext="webm")
    media[0]["formats"][1].update(acodec="vorbis", ext="ogg")
    report = local_engine(monkeypatch, media).download(
        URL,
        tmp_path / "converted",
        False,
        Preferences(audio_languages=languages, container="mp4"),
    )
    assert report["downloaded"], report["failed"]
    streams = probe(report["items"][0]["output"])["streams"]
    assert [s["codec_name"] for s in streams] == ["h264", *["aac" for _ in languages]]
