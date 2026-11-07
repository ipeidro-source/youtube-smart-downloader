import json
import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest

from youtube_smart_downloader.processes import Cancelled
from youtube_smart_downloader.tools import SPECS, ToolManager, ToolStatus, parse_winget_row


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_smart_downloader.tools.windows_supported", lambda: True)
    monkeypatch.setattr("youtube_smart_downloader.tools.shutil.which", lambda name: name + ".exe")
    return ToolManager(threading.Event(), tmp_path / "updates.json")


def installed(tmp_path):
    return [
        ToolStatus(
            spec,
            path=str(
                tmp_path
                / "Microsoft/WinGet/Packages"
                / (spec.package + "_source")
                / (spec.name + ".exe")
            ),
            version="1.0",
        )
        for spec in SPECS
    ]


def test_probe_checks_version_commands_not_only_path(manager, monkeypatch):
    outputs = {
        "yt-dlp.exe": "2026.10.26\n",
        "ffmpeg.exe": "ffmpeg version N-1234-test Copyright\n",
        "ffprobe.exe": "ffprobe version N-1234-test Copyright\n",
        "deno.exe": "deno 2.5.0 (stable)\nv8 1.0",
    }
    run = Mock(side_effect=lambda command, **kwargs: outputs[command[0]])
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = manager.probe()
    assert all(s.usable for s in statuses)
    assert [s.version for s in statuses] == ["2026.10.26", "N-1234-test", "N-1234-test", "2.5.0"]
    assert [call.args[0][1] for call in run.call_args_list] == [
        "--version",
        "-version",
        "-version",
        "--version",
    ]
    assert all(call.kwargs["timeout"] == 5 for call in run.call_args_list)


def test_probe_distinguishes_missing_broken_and_unrecognized_tools(manager, monkeypatch):
    monkeypatch.setattr(
        "youtube_smart_downloader.tools.shutil.which",
        lambda name: None if name == "ffprobe" else name,
    )

    def run(command, **kwargs):
        if command[0] == "ffmpeg":
            raise RuntimeError("broken executable")
        if command[0] == "deno":
            raise TimeoutError("silent tool")
        return "not a version"

    monkeypatch.setattr(manager.runner, "run", run)
    statuses = manager.probe()
    assert not any(s.usable for s in statuses)
    assert "Unrecognized" in statuses[0].error
    assert "broken" in statuses[1].error
    assert not statuses[2].path
    assert "silent" in statuses[3].error


@pytest.mark.parametrize(
    "output,expected",
    [
        (
            "Name Id Version Available Source\nTool   yt-dlp.yt-dlp   2026.01.01   2026.10.26   winget",
            ("2026.01.01", "2026.10.26"),
        ),
        ("Nombre Id Version Origen\nTool yt-dlp.yt-dlp 2026.10.26 winget", ("2026.10.26", None)),
        ("Tool yt-dlp.yt-dlp Unknown 2026.10.26 winget", None),
        ("Tool yt-dlp.yt-dlp-other 1.0 2.0 winget", None),
        ("No installed package found", None),
        (
            "Name   Id            Version\n------------------------\nyt-dlp yt-dlp.yt-dlp 2026.10.26",
            ("2026.10.26", None),
        ),
        ("yt-dlp yt-dlp.yt-dlp 2026.01.01 2026.10.26", ("2026.01.01", "2026.10.26")),
        ("Tool yt-dlp.yt-dlp 1.0 not-winget", None),
        ("\x1b[32mTool yt-dlp.yt-dlp 1.0 2.0 winget\x1b[0m", ("1.0", "2.0")),
    ],
)
def test_update_parser_is_conservative_and_independent_of_headers(output, expected):
    assert parse_winget_row(output, "yt-dlp.yt-dlp") == expected


def test_update_checks_only_three_packages_and_reuses_valid_cache(manager, monkeypatch, tmp_path):
    run = Mock(
        side_effect=lambda command, **kwargs: (
            f"Tool {command[command.index('--id') + 1]} 1.0 2.0 winget"
        )
    )
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = installed(tmp_path)
    first = manager.check_updates(statuses)
    assert all(s.update == "available" and s.available_version == "2.0" for s in first)
    assert run.call_count == 3  # ffmpeg and ffprobe share a package.
    second = manager.check_updates(statuses)
    assert second == first and run.call_count == 3
    assert all("upgrade" not in call.args[0] for call in run.call_args_list)
    # A changed executable invalidates the cache.
    manager.check_updates([replace(statuses[0], version="1.1"), *statuses[1:]])
    assert run.call_count == 6


def test_up_to_date_tools_need_no_update_action(manager, monkeypatch, tmp_path):
    monkeypatch.setattr(
        manager.runner,
        "run",
        lambda command, **kwargs: f"Tool {command[command.index('--id') + 1]} 1.0 winget",
    )
    statuses = manager.check_updates(installed(tmp_path))
    assert all(s.usable and s.update == "current" for s in statuses)


@pytest.mark.parametrize(
    "failure", [RuntimeError("offline"), TimeoutError("slow"), OSError("unavailable")]
)
def test_query_failure_allows_working_tools_and_is_not_cached_as_current(
    manager, monkeypatch, tmp_path, failure
):
    run = Mock(side_effect=failure)
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = manager.check_updates(installed(tmp_path))
    assert all(s.usable and s.update == "unknown" for s in statuses)
    assert not manager.cache_path.exists()


def test_manual_executables_are_not_claimed_to_be_up_to_date(manager, monkeypatch):
    run = Mock()
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = manager.check_updates(
        [ToolStatus(SPECS[0], path="C:/manual/yt-dlp.exe", version="2026.10.26")]
    )
    assert statuses[0].usable and statuses[0].update == "unknown"
    run.assert_not_called()


def test_missing_winget_does_not_block_installed_tools(manager, monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_smart_downloader.tools.shutil.which", lambda name: None)
    statuses = manager.check_updates(installed(tmp_path))
    assert all(s.usable and s.update == "unknown" for s in statuses)


@pytest.mark.parametrize("content", ["not json", "[]", '{"fingerprint": []}', '{"time": null}'])
def test_invalid_update_cache_is_ignored(manager, monkeypatch, tmp_path, content):
    manager.cache_path.write_text(content)
    monkeypatch.setattr(
        manager.runner,
        "run",
        lambda command, **kwargs: f"Tool {command[command.index('--id') + 1]} 1.0 winget",
    )
    assert all(s.update == "current" for s in manager.check_updates(installed(tmp_path)))


def test_expired_cache_is_refreshed(manager, monkeypatch, tmp_path):
    run = Mock(
        side_effect=lambda command, **kwargs: (
            f"Tool {command[command.index('--id') + 1]} 1.0 winget"
        )
    )
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = installed(tmp_path)
    manager.check_updates(statuses)
    cache = json.loads(manager.cache_path.read_text())
    cache["time"] -= manager.CACHE_SECONDS + 1
    manager.cache_path.write_text(json.dumps(cache))
    manager.check_updates(statuses)
    assert run.call_count == 6


def test_installation_is_scoped_and_deduplicates_ffmpeg_package(manager, monkeypatch):
    run = Mock(return_value="")
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = [ToolStatus(spec, error="missing") for spec in SPECS]
    manager.maintain(statuses, Mock(), update=False)
    assert run.call_count == 3
    assert all(call.args[0][1] == "install" for call in run.call_args_list)
    assert all("--all" not in call.args[0] for call in run.call_args_list)


def test_updates_only_confirmed_available_packages(manager, monkeypatch, tmp_path):
    run = Mock(return_value="")
    monkeypatch.setattr(manager.runner, "run", run)
    statuses = installed(tmp_path)
    statuses[0] = replace(statuses[0], update="available", available_version="2.0")
    manager.maintain(statuses, Mock(), update=True)
    command = run.call_args.args[0]
    assert run.call_count == 1 and command[1] == "upgrade"
    assert command[command.index("--id") + 1] == "yt-dlp.yt-dlp"
    assert "--all" not in command


def test_tool_checks_and_maintenance_can_be_cancelled_before_spawning(
    manager, monkeypatch, tmp_path
):
    run = Mock()
    monkeypatch.setattr(manager.runner, "run", run)
    manager.runner.cancel_event.set()
    with pytest.raises(Cancelled):
        manager.probe()
    with pytest.raises(Cancelled):
        manager.check_updates(installed(tmp_path))
    with pytest.raises(Cancelled):
        manager.maintain([ToolStatus(SPECS[0])], Mock(), update=False)
    run.assert_not_called()
