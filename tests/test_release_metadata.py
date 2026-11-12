"""Reject inconsistent release identities and invalid native Windows versions."""

import ast
from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from youtube_smart_downloader.release_metadata import load_release_metadata


ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_matches_project_owner_and_runtime():
    metadata = load_release_metadata(ROOT)
    assert metadata.company == "ipeidro"
    assert metadata.product == "YouTube Smart Downloader"
    assert metadata.strings["OriginalFilename"] == "YouTubeSmartDownloader.exe"
    assert metadata.strings["FileVersion"] == metadata.strings["ProductVersion"]
    assert metadata.version_tuple == tuple(int(p) for p in metadata.version.split(".")) + (0,)


@pytest.mark.parametrize("version", ["1.2", "1.2.3rc1", "1.2.3.4", "65536.0.0", "1.-2.0"])
def test_reject_versions_that_cannot_represent_a_stable_windows_release(version):
    with pytest.raises(ValueError):
        replace(load_release_metadata(ROOT), version=version).version_tuple


def test_resource_preserves_unicode_quotes_and_backslashes():
    metadata = replace(load_release_metadata(ROOT), company="Ipeidro's \\ café")
    tree = ast.parse(metadata.version_resource())
    strings = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    assert metadata.company in strings


def test_build_rejects_runtime_version_different_from_package(tmp_path):
    shutil.copyfile(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    module = tmp_path / "src/youtube_smart_downloader/__init__.py"
    module.parent.mkdir(parents=True)
    module.write_text('__version__ = "999.0.0"', encoding="utf-8")
    with pytest.raises(ValueError, match="same version"):
        load_release_metadata(tmp_path)
