"""Check actual Tk/CTk startup in the packaged executable, without user dialogs."""

import json
import argparse
import tempfile
import threading
from pathlib import Path

from youtube_smart_downloader.processes import Cancelled, ProcessRunner


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=root / "dist/YouTubeSmartDownloader.exe")
    executable = parser.parse_args().executable.resolve()
    with tempfile.TemporaryDirectory(prefix="ytsd-smoke-") as folder:
        result = Path(folder) / "startup.json"
        event = threading.Event()
        timeout = threading.Timer(45, event.set)
        timeout.start()
        try:
            ProcessRunner(event).run([str(executable), "--smoke-test", str(result)])
        except Cancelled as exc:
            raise SystemExit(
                "The executable did not finish its startup check within 45 seconds"
            ) from exc
        finally:
            timeout.cancel()
        if (
            not result.exists()
            or json.loads(result.read_text(encoding="utf-8")).get("status") != "ok"
        ):
            raise SystemExit("The executable did not confirm UI startup")
    print("OK: the executable initialized CustomTkinter and processed events.")


if __name__ == "__main__":
    main()
