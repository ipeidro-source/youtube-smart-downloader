"""Export the selected, unmodified design to PNG and Windows ICO sizes."""

from pathlib import Path

from PIL import Image


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "src/youtube_smart_downloader/assets"
    destination.mkdir(parents=True, exist_ok=True)
    with Image.open(root / "assets/app-icon-source.png") as source:
        icon = source.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
        icon.save(destination / "app-icon.png")
        icon.save(
            destination / "app-icon.ico",
            sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)],
        )


if __name__ == "__main__":
    main()
