import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from youtube_smart_downloader.core import Preferences
from youtube_smart_downloader.engine import Cancelled, DownloadEngine
from youtube_smart_downloader.storage import archive_video
from youtube_smart_downloader.requests import DownloadRequest, TimeRange


URL = "https://www.youtube.com/watch?v=abcdefghijk"
METADATA = {
    "id": "abcdefghijk",
    "title": "Sample",
    "duration": 10,
    "formats": [
        {"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080},
        {"format_id": "251-es", "vcodec": "none", "acodec": "opus", "language": "es", "abr": 128},
        {
            "format_id": "251-en",
            "vcodec": "none",
            "acodec": "opus",
            "language": "en",
            "format_note": "English (original)",
        },
    ],
}


@pytest.fixture
def engine(monkeypatch):
    instance = DownloadEngine(Mock(), Mock())
    monkeypatch.setattr(instance, "missing_tools", lambda: [])
    monkeypatch.setattr(instance, "_metadata", Mock(return_value=copy.deepcopy(METADATA)))
    return instance


def fake_download(arguments, **kwargs):
    directory = Path(arguments[arguments.index("-P") + 1])
    source = json.loads(
        Path(arguments[arguments.index("--load-info-json") + 1]).read_text(encoding="utf-8")
    )
    (directory / (source["id"] + ".mp4")).write_bytes(b"fixture")
    return ""


def test_clips_have_separate_archive_names_workdirs_and_expected_duration(
    engine, monkeypatch, tmp_path
):
    archive_video(tmp_path, "abcdefghijk")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert "--force-keyframes-at-cuts" not in arguments
        return fake_download(arguments)

    verify = Mock()
    monkeypatch.setattr(engine, "_run", run)
    monkeypatch.setattr(engine, "_verify_media", verify)
    prefs = Preferences(playlist_subfolder=False)
    requests = [DownloadRequest(URL, TimeRange(1, 4)), DownloadRequest(URL, TimeRange(4))]
    report = engine.download(requests, tmp_path, False, prefs)
    assert len(report["downloaded"]) == 2
    assert [args[args.index("--download-sections") + 1] for args in calls] == ["*1-4", "*4-inf"]
    assert calls[0][calls[0].index("-P") + 1] != calls[1][calls[1].index("-P") + 1]
    assert [call.args[1] for call in verify.call_args_list] == [3, 6]
    assert all(call.kwargs == {"clip": True} for call in verify.call_args_list)
    assert report["items"][0]["time_range"] == {"start": 1, "end": 4}
    assert "1-4s" in report["items"][0]["output"]
    assert (tmp_path / ".ytsd-archive.txt").read_text() == "youtube abcdefghijk\n"
    again = engine.download(requests, tmp_path, False, prefs)
    assert len(again["archived"]) == 2 and len(calls) == 2


def test_clip_does_not_archive_full_video(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", Mock())
    prefs = Preferences(playlist_subfolder=False)
    report = engine.download(DownloadRequest(URL, TimeRange(1, 4)), tmp_path, False, prefs)
    assert report["downloaded"]
    assert not (tmp_path / ".ytsd-archive.txt").exists()
    report = engine.download(URL, tmp_path, False, prefs)
    assert report["downloaded"] and not report["archived"]


@pytest.mark.parametrize(
    "duration,time_range",
    [
        (None, TimeRange(1)),
        (0, TimeRange(1)),
        (float("nan"), TimeRange(1)),
        (10, TimeRange(10)),
        (10, TimeRange(0, 11)),
    ],
)
def test_invalid_clip_bounds_fail_before_downloading(
    engine, monkeypatch, tmp_path, duration, time_range
):
    engine._metadata.return_value["duration"] = duration
    run = Mock()
    monkeypatch.setattr(engine, "_run", run)
    report = engine.download(DownloadRequest(URL, time_range), tmp_path, False, Preferences())
    assert report["failed"] and not report["downloaded"]
    assert report["items"][0]["time_range"]["start"] == time_range.start
    run.assert_not_called()


def test_invalid_clip_does_not_stop_batch(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", Mock())
    report = engine.download(
        [DownloadRequest(URL, TimeRange(10)), DownloadRequest(URL, TimeRange(1, 3))],
        tmp_path,
        False,
        Preferences(),
    )
    assert len(report["failed"]) == len(report["downloaded"]) == 1


def test_playlist_range_rejected(engine, tmp_path):
    with pytest.raises(ValueError, match="Playlists"):
        engine.download(DownloadRequest(URL, TimeRange(1)), tmp_path, True, Preferences())


def test_failed_metadata_keeps_requested_range_in_report(engine, tmp_path):
    engine._metadata.side_effect = RuntimeError("Unavailable video")
    report = engine.download(DownloadRequest(URL, TimeRange(1, 3)), tmp_path, False, Preferences())
    assert report["items"][0]["time_range"] == {"start": 1, "end": 3}


@pytest.mark.parametrize("duration,expected,valid", [(3, 1, True), (10, 1, False), (1, 10, False)])
def test_clip_verification_tolerates_fast_cuts_but_rejects_wrong_duration(
    engine, tmp_path, duration, expected, valid
):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fixture")
    engine.runner.run = Mock(
        return_value=json.dumps(
            {
                "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
                "format": {"duration": duration, "format_name": "mov,mp4"},
            }
        )
    )
    if valid:
        engine._verify_media(path, expected, clip=True)
    else:
        with pytest.raises(RuntimeError):
            engine._verify_media(path, expected, clip=True)


def test_success_requires_validation_before_archive(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)

    def verify(path, duration):
        assert path.read_bytes() == b"fixture"
        assert not (tmp_path / ".ytsd-archive.txt").exists()

    monkeypatch.setattr(engine, "_verify_media", verify)
    report = engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    assert len(report["downloaded"]) == 1
    assert report["state"] == "completed"
    assert (tmp_path / "Sample [abcdefghijk].mp4").read_bytes() == b"fixture"
    assert "youtube abcdefghijk" in (tmp_path / ".ytsd-archive.txt").read_text()
    assert json.loads(Path(report["report_path"]).read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("failure", ["process", "probe", "missing_output"])
def test_failures_are_not_archived(engine, monkeypatch, tmp_path, failure):
    def run(arguments, **kwargs):
        if failure == "process":
            raise RuntimeError("Postprocessing failed")
        return fake_download(arguments) if failure == "probe" else ""

    monkeypatch.setattr(engine, "_run", run)
    if failure == "probe":
        monkeypatch.setattr(engine, "_verify_media", Mock(side_effect=RuntimeError("invalid")))
    report = engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    assert report["state"] == "completed_with_errors"
    assert report["failed"] and not report["downloaded"]
    assert not (tmp_path / ".ytsd-archive.txt").exists()
    assert not list(tmp_path.glob("*.mp4"))


def test_archived_video_is_not_claimed_as_a_new_download(engine, tmp_path):
    archive_video(tmp_path, "abcdefghijk")
    report = engine.download(
        URL, tmp_path, False, Preferences(language="es-ES", playlist_subfolder=False)
    )
    assert report["archived"] == ["Sample"]
    assert not report["downloaded"]
    assert "verified" not in report["items"][0]


def test_cancelled_before_start_never_fetches_metadata(engine, tmp_path):
    engine.cancel()
    with pytest.raises(Cancelled):
        engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    engine._metadata.assert_not_called()
    assert json.loads((tmp_path / "download-report.json").read_text())["state"] == "cancelled"


def test_cancel_keeps_previous_results_and_session_reports(engine, monkeypatch, tmp_path):
    def metadata(url, flat=False):
        if flat:
            return {"entries": [{"url": URL}, {"url": URL}]}
        return copy.deepcopy(METADATA)

    monkeypatch.setattr(engine, "_metadata", metadata)
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    engine.progress = lambda *args: engine.cancel()
    with pytest.raises(Cancelled):
        engine.download(URL, tmp_path, True, Preferences(playlist_subfolder=False))
    report = json.loads((tmp_path / "download-report.json").read_text(encoding="utf-8"))
    assert report["state"] == "cancelled" and len(report["downloaded"]) == 1
    first_path = Path(report["report_path"])
    # A new job preserves the cancelled session, even though latest is replaced.
    other = DownloadEngine(Mock(), Mock())
    monkeypatch.setattr(other, "missing_tools", lambda: ["fixture"])
    with pytest.raises(RuntimeError):
        other.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    assert json.loads(first_path.read_text(encoding="utf-8"))["state"] == "cancelled"


def test_invalid_playlist_entries_do_not_abort_remaining_items(engine, monkeypatch, tmp_path):
    def metadata(url, flat=False):
        if flat:
            return {"entries": [None, {"id": "invalid"}, {"url": URL}]}
        return copy.deepcopy(METADATA)

    monkeypatch.setattr(engine, "_metadata", metadata)
    report = engine.download(
        URL, tmp_path, True, Preferences(language="es-ES", playlist_subfolder=False)
    )
    assert len(report["failed"]) == 2 and len(report["omitted"]) == 1
    assert engine.progress.call_args.args == (3, 3, "100%")


def test_fallback_does_not_verify_requested_language(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    report = engine.download(
        URL, tmp_path, False, Preferences(language="es-ES", missing="fallback")
    )
    item = report["items"][0]
    assert item["audio_language"] == "en"
    assert item["fallback"] and not item["verified"]


def test_resume_workdir_survives_title_and_index_changes(engine, monkeypatch, tmp_path):
    directories = []

    def run(arguments, **kwargs):
        directories.append(arguments[arguments.index("-P") + 1])
        raise Cancelled()

    monkeypatch.setattr(engine, "_run", run)
    with pytest.raises(Cancelled):
        engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    engine._metadata.return_value["title"] = "Changed title"
    # A fresh engine is required only if its cancellation event was set.
    with pytest.raises(Cancelled):
        engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    assert directories[0] == directories[1]


def test_valid_staged_result_recovers_without_redownloading(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", Mock(side_effect=Cancelled()))
    with pytest.raises(Cancelled):
        engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    run = Mock(side_effect=AssertionError("should reuse staged output"))
    monkeypatch.setattr(engine, "_run", run)
    assert engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))[
        "downloaded"
    ]
    run.assert_not_called()


def test_invalid_staged_result_is_regenerated(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", Mock(side_effect=RuntimeError("truncated")))
    assert engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))["failed"]
    verify = Mock(side_effect=[RuntimeError("truncated"), None])
    monkeypatch.setattr(engine, "_verify_media", verify)
    assert engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))[
        "downloaded"
    ]
    assert verify.call_count == 2


def test_existing_user_file_is_never_overwritten(engine, monkeypatch, tmp_path):
    destination = tmp_path / "Sample [abcdefghijk].mp4"
    destination.write_bytes(b"user file")
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    assert engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))["failed"]
    assert destination.read_bytes() == b"user file"
    assert not (tmp_path / ".ytsd-archive.txt").exists()


def test_yt_dlp_does_not_load_external_configuration(monkeypatch):
    run = Mock(return_value='WARNING: fixture\n{"id":"abcdefghijk"}')
    actual = DownloadEngine(Mock(), Mock())
    monkeypatch.setattr(actual.runner, "run", run)
    assert actual._metadata(URL)["id"] == "abcdefghijk"
    assert "--ignore-config" in run.call_args.args[0]


def test_download_uses_the_inspected_tracks_without_reextracting(engine, monkeypatch, tmp_path):
    def run(arguments, **kwargs):
        assert URL not in arguments
        snapshot = json.loads(
            Path(arguments[arguments.index("--load-info-json") + 1]).read_text(encoding="utf-8")
        )
        assert {track["format_id"] for track in snapshot["formats"]} == {"137", "251-es"}
        assert snapshot["formats"][1]["language"] == "es"
        assert "requested_formats" not in snapshot and "_filename" not in snapshot
        return fake_download(arguments)

    engine._metadata.return_value.update(
        requested_formats=[METADATA["formats"][-1]], _filename="old.mp4"
    )
    monkeypatch.setattr(engine, "_run", run)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    assert engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))[
        "downloaded"
    ]
    assert engine._metadata.call_count == 1


def test_txt_queue_has_one_ordered_report_and_numbered_outputs(engine, monkeypatch, tmp_path):
    links = [URL, "https://www.youtube.com/watch?v=12345678901"]

    def metadata(url, **kwargs):
        result = copy.deepcopy(METADATA)
        result["id"] = url[-11:]
        return result

    monkeypatch.setattr(engine, "_metadata", metadata)
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    report = engine.download(links, tmp_path, False, Preferences(playlist_subfolder=False))
    assert len(report["downloaded"]) == 2
    assert [item["url"] for item in report["items"]] == links
    assert (tmp_path / "001 - Sample [abcdefghijk].mp4").exists()
    assert (tmp_path / "002 - Sample [12345678901].mp4").exists()
    assert len(list((tmp_path / ".ytsd-reports").glob("*.json"))) == 1
    assert engine.progress.call_args.args == (2, 2, "100%")


def test_batch_cancellation_keeps_previous_results(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    engine.progress = lambda *args: engine.cancel()
    with pytest.raises(Cancelled):
        engine.download([URL, URL], tmp_path, False, Preferences(playlist_subfolder=False))
    assert engine.report["state"] == "cancelled"
    assert len(engine.report["downloaded"]) == 1


def test_reports_keep_ids_and_add_readable_metadata(engine, monkeypatch, tmp_path):
    engine._metadata.return_value["formats"][0].update(width=1920, height=1080, fps=30, ext="mp4")
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    report = engine.download(URL, tmp_path, False, Preferences(playlist_subfolder=False))
    item = report["items"][0]
    assert item["video_format"] == "137" and item["audio_format"] == "251-es"
    assert item["video_details"]["description"] == "1920x1080 | 30 fps | H.264"
    assert "Spanish" in item["audio_details"]["description"]
    assert "Opus" in item["audio_details"]["description"]


@pytest.mark.parametrize(
    "kind,name", [("video", "Sample"), ("playlist", "My playlist"), ("txt", "My links")]
)
@pytest.mark.parametrize("enabled", [True, False])
def test_subfolder_follows_input_name_for_all_sources(
    engine, monkeypatch, tmp_path, kind, name, enabled
):
    def metadata(url, flat=False):
        return (
            {"title": "My playlist", "entries": [{"url": URL}]} if flat else copy.deepcopy(METADATA)
        )

    monkeypatch.setattr(engine, "_metadata", metadata)
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    report = engine.download(
        [URL] if kind == "txt" else URL,
        tmp_path,
        kind == "playlist",
        Preferences(playlist_subfolder=enabled),
        batch_name="My links" if kind == "txt" else None,
    )
    destination = tmp_path / name if enabled else tmp_path
    assert Path(report["directory"]) == destination
    assert len(report["downloaded"]) == 1
    assert Path(report["items"][0]["output"]).parent == destination
    assert (destination / ".ytsd-archive.txt").is_file()
    assert (destination / "download-report.json").is_file()
    assert not (tmp_path / name / name).exists()
    assert not list(destination.glob("*/Sample [abcdefghijk].mp4"))
    if not enabled:
        assert not (tmp_path / name).exists()


def test_subfolder_names_are_safe_on_windows(engine, monkeypatch, tmp_path):
    engine._metadata.return_value["title"] = "CON"
    monkeypatch.setattr(engine, "_run", fake_download)
    monkeypatch.setattr(engine, "_verify_media", lambda *args: None)
    report = engine.download(URL, tmp_path, False, Preferences())
    assert Path(report["directory"]) == tmp_path / "_CON"
    assert report["downloaded"]


def test_skipped_video_still_creates_its_named_folder(engine, tmp_path):
    report = engine.download(URL, tmp_path, False, Preferences(language="es-ES"))
    assert (tmp_path / "Sample").is_dir()
    assert report["omitted"]
    assert Path(report["directory"]) == tmp_path / "Sample"
