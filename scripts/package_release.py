"""Package the final tested executable and its notices; hash the published files."""

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from youtube_smart_downloader.release_metadata import load_release_metadata


def package_release(directory: Path, version: str) -> tuple[Path, Path]:
    names = (
        "YouTubeSmartDownloader.exe",
        "LICENSE.txt",
        "THIRD_PARTY_NOTICES.txt",
        "THIRD_PARTY_COMPONENTS.json",
        "THIRD_PARTY.md",
        "PRIVACY.md",
        "UNINSTALL.md",
    )
    for name in names:
        if not (directory / name).is_file():
            raise ValueError(f"Missing release file: {name}")
    bundle = directory / f"YouTubeSmartDownloader-{version}-Windows-x64.zip"
    with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(directory / name, arcname=name)
    checksums = directory / "SHA256SUMS.txt"
    lines = []
    for path in (directory / names[0], bundle):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    checksums.write_text("".join(lines), encoding="utf-8")
    return bundle, checksums


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=root / "dist")
    directory = parser.parse_args().directory.resolve()
    metadata = load_release_metadata(root)
    bundle, checksums = package_release(directory, metadata.version)
    print(f"Created {bundle.name} and {checksums.name}")


if __name__ == "__main__":
    main()
