"""Reject tags that do not match both package version declarations."""

import os
import runpy
import tomllib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    module = runpy.run_path(str(root / "src/youtube_smart_downloader/__init__.py"))
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if module["__version__"] != version or tag != "v" + version:
        raise SystemExit(f"Tag {tag!r} and both package versions must match v{version}")


if __name__ == "__main__":
    main()
