import sys
import threading
import time
from unittest.mock import Mock

import pytest

from youtube_smart_downloader.processes import Cancelled, ProcessRunner


def test_error_text_is_failure_even_if_child_returns_zero():
    runner = ProcessRunner(threading.Event())
    with pytest.raises(RuntimeError, match="fixture"):
        runner.run([sys.executable, "-c", "print('ERROR: fixture')"])


def test_nonzero_return_is_failure():
    with pytest.raises(RuntimeError):
        ProcessRunner(threading.Event()).run([sys.executable, "-c", "raise SystemExit(2)"])


def test_pre_cancelled_job_does_not_spawn(monkeypatch):
    spawn = Mock()
    monkeypatch.setattr("subprocess.Popen", spawn)
    event = threading.Event()
    event.set()
    with pytest.raises(Cancelled):
        ProcessRunner(event).run(["not-started"])
    spawn.assert_not_called()


def test_cancel_stops_silent_child_without_waiting_for_output():
    event = threading.Event()
    timer = threading.Timer(0.3, event.set)
    timer.start()
    try:
        with pytest.raises(Cancelled):
            ProcessRunner(event).run([sys.executable, "-c", "import time; time.sleep(30)"])
    finally:
        timer.cancel()


def test_output_is_bounded_except_metadata():
    runner = ProcessRunner(threading.Event())
    command = [sys.executable, "-c", "for i in range(100): print(i)"]
    assert len(runner.run(command).splitlines()) == 30
    assert len(runner.run(command, capture_all=True).splitlines()) == 100


def test_cancellation_also_stops_descendants(tmp_path):
    event = threading.Event()
    survivor = tmp_path / "surviving-child.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(1.5); Path("
        + repr(str(survivor))
        + ").write_text('survived')"
    )
    parent = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', "
        + repr(child)
        + "]); print('READY', flush=True); time.sleep(30)"
    )
    watchdog = threading.Timer(5, event.set)
    watchdog.start()
    try:
        with pytest.raises(Cancelled):
            ProcessRunner(event).run(
                [sys.executable, "-c", parent],
                on_line=lambda line: event.set() if line == "READY" else None,
            )
    finally:
        watchdog.cancel()
    time.sleep(1.8)
    assert not survivor.exists(), "A descendant process survived cancellation"


def test_timeout_stops_a_silent_process():
    with pytest.raises(TimeoutError, match="within"):
        ProcessRunner(threading.Event()).run(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2
        )
