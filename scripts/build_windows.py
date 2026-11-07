"""Shared local/CI Windows build recipe, including CustomTkinter assets."""

from pathlib import Path
import os
import argparse
from importlib.metadata import distribution
import json
import shutil
import sys

import PyInstaller.__main__

from youtube_smart_downloader.release_metadata import load_release_metadata


def prepare_notices(root: Path, target: Path) -> None:
    """Keep full license texts from the installed build inputs, without network access."""
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "LICENSE", target / "LICENSE.txt")
    for name in ("PRIVACY", "UNINSTALL", "CODE_SIGNING", "THIRD_PARTY"):
        shutil.copyfile(root / f"docs/{name}.md", target / f"{name}.md")
    sections = [
        (
            "Bundled components and licenses",
            (root / "docs/THIRD_PARTY.md").read_text(encoding="utf-8"),
        )
    ]
    components: list[dict[str, str]] = []
    for name in (
        "customtkinter",
        "darkdetect",
        "packaging",
        "pillow",
        "typing_extensions",
        "pyinstaller",
    ):
        package = distribution(name)
        licenses = [
            item
            for item in package.files or []
            if ".dist-info/" in str(item).replace("\\", "/")
            and item.name.lower().startswith(("license", "copying", "notice"))
        ]
        if not licenses:
            raise RuntimeError(f"No installed license text found for {name}")
        components.append({"name": name, "version": package.version})
        for license_item in sorted(licenses):
            sections.append(
                (
                    f"{name} {package.version} / {license_item.name}",
                    Path(str(package.locate_file(license_item))).read_text(encoding="utf-8"),
                )
            )
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The Windows Python installation must include LICENSE.txt")
    sections.append(
        (
            f"Python {sys.version.split()[0]} and included third-party notices",
            python_license.read_text(encoding="utf-8"),
        )
    )
    components.append({"name": "Python", "version": sys.version.split()[0]})
    tk_licenses = sorted((Path(sys.base_prefix) / "tcl").glob("tk*/license.terms"))
    if not tk_licenses:
        raise RuntimeError("The Windows Python installation must include the Tk license")
    for item in tk_licenses:
        sections.append((f"Tk / {item.parent.name}", item.read_text(encoding="utf-8")))
    for filename in ("Roboto-LICENSE.txt", "Tcl-LICENSE.txt", "OpenSSL-LICENSE.txt"):
        item = root / "licenses" / filename
        sections.append((item.stem, item.read_text(encoding="utf-8")))
    (target / "THIRD_PARTY_NOTICES.txt").write_text(
        "\n\n".join(f"{'=' * 72}\n{title}\n{'=' * 72}\n{text}" for title, text in sections),
        encoding="utf-8",
    )
    (target / "THIRD_PARTY_COMPONENTS.json").write_text(
        json.dumps({"build_inputs": components}, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The Windows executable must be built on Windows")
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    args = parser.parse_args()
    metadata = load_release_metadata(root)
    resources = root / "build/release-resources"
    resources.mkdir(parents=True, exist_ok=True)
    version_file = resources / "windows-version.txt"
    version_file.write_text(metadata.version_resource(), encoding="utf-8")
    notices = resources / "release-docs"
    prepare_notices(root, notices)
    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--version-file",
            str(version_file),
            "--add-data",
            f"{notices}{os.pathsep}release-docs",
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
    for item in notices.iterdir():
        shutil.copyfile(item, args.dist_dir.resolve() / item.name)


if __name__ == "__main__":
    main()
