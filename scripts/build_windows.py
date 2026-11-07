"""Shared local/CI Windows build recipe, including CustomTkinter assets."""

from pathlib import Path
import os
import argparse

import PyInstaller.__main__


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The Windows executable must be built on Windows")
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    args = parser.parse_args()
    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--icon",
            str(root / "src/youtube_smart_downloader/assets/app-icon.ico"),
            "--name",
            "YouTubeSmartDownloader",
            "--distpath",
            str(args.dist_dir.resolve()),
            "--paths",
            str(root / "src"),
            "--collect-all",
            "customtkinter",
            "--collect-data",
            "youtube_smart_downloader",
            "--specpath",
            str(root / "build"),
            str(root / "src/youtube_smart_downloader/__main__.py"),
        ]
    )


if __name__ == "__main__":
    main()
