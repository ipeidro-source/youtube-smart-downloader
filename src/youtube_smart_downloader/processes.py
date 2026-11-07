"""Cancellable subprocesses. Cancellation never blocks the Tk event loop."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Callable


class Cancelled(Exception):
    """The operation was cancelled and its child processes have been stopped."""


class ProcessRunner:
    def __init__(self, cancel_event: threading.Event) -> None:
        self.cancel_event = cancel_event

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
                if result.returncode and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                    detail = result.stderr.decode(errors="replace")[-300:]
                    raise RuntimeError(
                        f"Could not confirm termination of the process tree: {detail}"
                    )
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError("Timed out while stopping the process tree") from exc
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)

    def run(
        self,
        command: list[str],
        *,
        capture_all: bool = False,
        on_line: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> str:
        self.check_cancelled()
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        output: queue.Queue[str | None] = queue.Queue(maxsize=256)
        reader_stop = threading.Event()

        def emit(line: str | None) -> None:
            while not reader_stop.is_set():
                try:
                    output.put(line, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def read() -> None:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    if reader_stop.is_set():
                        break
                    emit(line.rstrip("\r\n"))
            finally:
                emit(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        started = time.monotonic()

        def check() -> None:
            self.check_cancelled()
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"{command[0]} did not finish within {timeout:g} seconds")

        lines: list[str] | deque[str] = [] if capture_all else deque(maxlen=30)
        error_line = ""
        try:
            while True:
                check()
                try:
                    line = output.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                lines.append(line)
                if line.startswith("ERROR:"):
                    error_line = line
                if on_line:
                    on_line(line)
            while process.poll() is None:
                check()
                self.cancel_event.wait(0.1)
            self.check_cancelled()
            if process.returncode or error_line:
                detail = error_line or " ".join(list(lines)[-5:])
                raise RuntimeError(f"{command[0]} failed: {detail[-700:]}")
            return "\n".join(lines)
        finally:
            reader_stop.set()
            try:
                self._stop(process)
            finally:
                reader.join(timeout=2)
                if not reader.is_alive() and process.stdout is not None:
                    process.stdout.close()
