"""Read PE resources and embedded notices without executing the downloaded binary."""

import argparse
import os
from pathlib import Path

from youtube_smart_downloader.release_metadata import load_release_metadata


def main() -> None:
    if os.name != "nt":
        raise SystemExit("PE validation must run on Windows")
    import pefile
    from PyInstaller.archive.readers import CArchiveReader

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=root / "dist/YouTubeSmartDownloader.exe")
    executable = parser.parse_args().executable.resolve()
    expected = load_release_metadata(root)
    strings: dict[str, str] = {}
    with pefile.PE(str(executable)) as image:
        for group in getattr(image, "FileInfo", []):
            for entry in group:
                for table in getattr(entry, "StringTable", []):
                    strings.update(
                        {k.decode("utf-8"): v.decode("utf-8") for k, v in table.entries.items()}
                    )
        for key, value in expected.strings.items():
            if strings.get(key) != value:
                raise SystemExit(f"Invalid {key}: {strings.get(key)!r}; expected {value!r}")
        fixed = image.VS_FIXEDFILEINFO[0]
        major, minor, patch, revision = expected.version_tuple
        for prefix in ("File", "Product"):
            if (
                getattr(fixed, f"{prefix}VersionMS") != (major << 16) | minor
                or getattr(fixed, f"{prefix}VersionLS") != (patch << 16) | revision
            ):
                raise SystemExit(f"Invalid fixed {prefix} version")
    archive = CArchiveReader(str(executable))
    for name in (
        "LICENSE.txt",
        "THIRD_PARTY_NOTICES.txt",
        "THIRD_PARTY_COMPONENTS.json",
        "THIRD_PARTY.md",
        "PRIVACY.md",
        "UNINSTALL.md",
        "CODE_SIGNING.md",
    ):
        archive_key = next(
            (key for key in archive.toc if key.replace("\\", "/") == f"release-docs/{name}"), None
        )
        if archive_key is None or not archive.extract(archive_key):
            raise SystemExit(f"Missing embedded release document: {name}")
        companion = executable.parent / name
        if not companion.is_file() or companion.read_bytes() != archive.extract(archive_key):
            raise SystemExit(f"Release document differs from the embedded copy: {name}")
    print(f"OK: PE identity, version {expected.version}, and embedded release documents.")


if __name__ == "__main__":
    main()
