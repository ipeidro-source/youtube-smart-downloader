import json
import threading
from unittest.mock import Mock

import pytest

from youtube_smart_downloader.core import Preferences
from youtube_smart_downloader.engine import DownloadEngine
from youtube_smart_downloader.settings import normalize
from youtube_smart_downloader.tools import ToolManager, parse_impersonation_targets


def test_available_browser_families_exclude_unavailable_profiles():
    output = """Client OS Source
Chrome-120 Windows-10 curl_cffi
Chrome-152 Macos-26 curl_cffi
Firefox-155 Windows-10 curl_cffi
Safari-27 Macos-27 curl_cffi (not available)
"""
    assert parse_impersonation_targets(output) == ["chrome", "firefox"]
    manager = ToolManager(threading.Event())
    manager.runner.run = Mock(side_effect=RuntimeError("not supported"))
    assert manager.impersonation_targets() == []


@pytest.mark.parametrize("profile", ["auto", "chrome", "firefox"])
def test_profile_applies_to_metadata_media_and_subtitles(profile):
    engine = DownloadEngine(Mock(), Mock())
    engine.impersonation = profile
    engine.runner.run = Mock(return_value=json.dumps({"id": "abcdefghijk"}))
    engine._metadata("https://youtu.be/abcdefghijk")
    engine._run(["--load-info-json", "media.json"])
    engine._run(["--skip-download", "--write-subs", "--load-info-json", "subs.json"])
    for call in engine.runner.run.call_args_list:
        command = call.args[0]
        assert ("--impersonate" in command) == (profile != "auto")
        if profile != "auto":
            assert command[command.index("--impersonate") + 1] == profile


def test_unavailable_forced_profile_fails_before_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(ToolManager, "impersonation_targets", lambda self: [])
    engine = DownloadEngine(Mock(), Mock())
    engine.missing_tools = Mock(return_value=[])
    engine._metadata = Mock()
    with pytest.raises(ValueError, match="unavailable"):
        engine.download(
            "https://youtu.be/abcdefghijk", tmp_path, False, Preferences(impersonation="chrome")
        )
    engine._metadata.assert_not_called()
    assert engine.report["state"] == "failed"


def test_settings_default_validation_and_preserved_choice():
    assert normalize({})["impersonation"] == "auto"
    assert normalize({"impersonation": "chrome"})["impersonation"] == "chrome"
    assert normalize({"impersonation": []})["impersonation"] == "auto"
    with pytest.raises(ValueError, match="impersonation"):
        Preferences(impersonation="--bad option").validate()
