"""Check the final distribution's contents and hashes, independent of signing."""

import hashlib
from pathlib import Path
import runpy
from zipfile import ZipFile

import pytest


PACKAGE_RELEASE = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/package_release.py")
)["package_release"]
FILES = (
    "YouTubeSmartDownloader.exe",
    "LICENSE.txt",
    "THIRD_PARTY_NOTICES.txt",
    "THIRD_PARTY_COMPONENTS.json",
    "THIRD_PARTY.md",
    "PRIVACY.md",
    "UNINSTALL.md",
    "CODE_SIGNING.md",
)


def test_portable_package_preserves_final_executable_and_publishes_matching_hashes(tmp_path):
    final_binary = b"final signed executable content\0\xff"
    for name in FILES:
        (tmp_path / name).write_bytes(final_binary if name.endswith(".exe") else name.encode())
    bundle, checksums = PACKAGE_RELEASE(tmp_path, "1.2.3")
    with ZipFile(bundle) as archive:
        assert set(archive.namelist()) == set(FILES)
        assert archive.read("YouTubeSmartDownloader.exe") == final_binary
    for line in checksums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
    assert len(checksums.read_text().splitlines()) == 2


def test_packaging_refuses_distribution_missing_license_notices(tmp_path):
    (tmp_path / "YouTubeSmartDownloader.exe").write_bytes(b"binary")
    with pytest.raises(ValueError, match="Missing release file: LICENSE.txt"):
        PACKAGE_RELEASE(tmp_path, "1.2.3")
    assert not list(tmp_path.glob("*.zip"))
