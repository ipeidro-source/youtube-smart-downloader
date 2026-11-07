"""Validated project identity shared by the Windows build and release checks."""

from dataclasses import dataclass
from pathlib import Path
import re
import runpy
import tomllib


@dataclass(frozen=True)
class ReleaseMetadata:
    version: str
    company: str
    product: str
    description: str
    copyright: str
    internal_name: str
    filename: str
    homepage: str
    support: str

    @property
    def version_tuple(self) -> tuple[int, int, int, int]:
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ValueError("Windows releases require a stable major.minor.patch version")
        major, minor, patch = (int(part) for part in self.version.split("."))
        if any(part > 65535 for part in (major, minor, patch)):
            raise ValueError("Windows version components must fit unsigned 16-bit integers")
        return major, minor, patch, 0

    @property
    def strings(self) -> dict[str, str]:
        return {
            "CompanyName": self.company,
            "FileDescription": self.description,
            "FileVersion": self.version,
            "InternalName": self.internal_name,
            "LegalCopyright": self.copyright,
            "OriginalFilename": self.filename,
            "ProductName": self.product,
            "ProductVersion": self.version,
            "Comments": f"Project: {self.homepage} | Support: {self.support} | License: MIT",
        }

    def version_resource(self) -> str:
        # repr preserves quotes, backslashes and Unicode in PyInstaller's Python resource file.
        values = ",\n".join(
            f"            StringStruct({k!r}, {v!r})" for k, v in self.strings.items()
        )
        return (
            "# Generated from pyproject.toml; do not edit.\n"
            "VSVersionInfo(\n"
            f"  ffi=FixedFileInfo(filevers={self.version_tuple!r}, prodvers={self.version_tuple!r},\n"
            "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
            "  kids=[StringFileInfo([StringTable('040904B0', [\n"
            f"{values}\n"
            "  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]\n"
            ")\n"
        )


def load_release_metadata(root: Path) -> ReleaseMetadata:
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]
    windows = document["tool"]["ytsd"]["windows"]
    metadata = ReleaseMetadata(
        version=project["version"],
        company=project["authors"][0]["name"],
        product=windows["product-name"],
        description=windows["file-description"],
        copyright=windows["copyright"],
        internal_name=windows["internal-name"],
        filename=windows["original-filename"],
        homepage=project["urls"]["Homepage"],
        support=project["urls"]["Issues"],
    )
    for key, value in metadata.strings.items():
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            raise ValueError(f"Invalid Windows metadata field: {key}")
    metadata.version_tuple
    module = runpy.run_path(str(root / "src/youtube_smart_downloader/__init__.py"))
    if module["__version__"] != metadata.version:
        raise ValueError("pyproject.toml and __version__ must declare the same version")
    return metadata
