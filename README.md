# YouTube Smart Downloader

A free, open-source Windows desktop application built with CustomTkinter and yt-dlp, with explicit audio-language selection.

Only download content when you have the necessary rights or permission.

## Features

- Automatically identify a YouTube video or playlist. Links containing both require an explicit choice.
- Import a UTF-8 TXT file with one video URL per line, preserving the order.
- Download optional time ranges for individual videos or per TXT entry, using fast cuts.
- Choose a destination folder and optionally create a subfolder named after the video, playlist or imported TXT file (without its extension).
- Select Spanish (any region), Spanish (Spain), Spanish (Latin America), English, original or automatic audio.
- Strict language matching: skip videos without a matching labelled track, or explicitly allow an unverified fallback.
- Choose the maximum resolution: best available, 1080p, 720p or 480p.
- MP4 output, progress, cancellation, resumable partial files and a per-folder archive.
- Incremental JSON reports with readable format descriptions and technical IDs.
- Startup tool checks and optional installation/updates using winget.

## Windows usage

1. Download the portable ZIP from [Releases](https://github.com/ipeidro-source/youtube-smart-downloader/releases) and extract it to keep the executable and its license/privacy documents together. The standalone `YouTubeSmartDownloader.exe` is also available.
2. Run the executable. Windows SmartScreen may ask you to verify its origin.
3. Startup checks yt-dlp, FFmpeg, ffprobe and Deno. If a tool is missing or unusable, install the listed dependencies or exit. FFmpeg includes ffprobe.
4. Working tools let you continue even when updates are available or update information cannot be obtained. The **Update tools** button appears only for confirmed updates.
5. Paste a YouTube link or select **Import links...**, choose the destination, language and quality, then select **Download**.
6. Use **About** to view the application version, author, technologies, project/support links and privacy policy. The **Licenses** tab displays the release's bundled license notices locally.

Python is not required for the executable. yt-dlp, FFmpeg/ffprobe and Deno are external tools; they are not bundled. Windows with winget and an internet connection is required for automatic installation. Manual installation is also supported. Restart the app after installation or updates if PATH has changed.

A Windows portable executable is distributed, not a setup wizard or MSI installer. Windows is the supported desktop platform. Linux CI checks shared Python logic; it does not provide a Linux release or GUI support guarantee.

Author and copyright holder: **ipeidro** ([@ipeidro-source](https://github.com/ipeidro-source)). Support: [GitHub Issues](https://github.com/ipeidro-source/youtube-smart-downloader/issues). See [Privacy](docs/PRIVACY.md) for network activity and local data, and [Uninstallation](docs/UNINSTALL.md) for removing the application and optional external tools.

## Input files

TXT files use UTF-8 (a BOM is accepted), one YouTube video URL per line. Blank lines and lines beginning with `#`, `;` or `]` are ignored. Playlists and ambiguous video/playlist links are rejected inside TXT files. Invalid lines and duplicate videos are listed before importing; no URLs are silently discarded. Imported videos use one ordered queue, one destination and one session report. When **Create a subfolder** is checked, all imported videos share a folder named after the TXT file without its extension. Importing a file does not add support for other video providers.

For a single video, optional **Start** and **End** fields select a time range. Enter whole seconds,
`MM:SS` or `HH:MM:SS` (for example `90`, `01:30` or `01:02:30`); minutes and seconds in
colon-separated values must be between 0 and 59. A blank start means zero; a blank end means
the end of the video. Both blank downloads the whole video. Times reset when the source changes
and are not saved as preferences. Time parameters in URLs are not used as download ranges.

TXT lines accept either a URL alone or exactly three semicolon-separated columns,
`URL;start;end`, with optional surrounding spaces:

```text
https://www.youtube.com/watch?v=abcdefghijk
https://www.youtube.com/watch?v=abcdefghijk;01:30;03:00
https://www.youtube.com/watch?v=abcdefghijk;01:30;
https://www.youtube.com/watch?v=abcdefghijk;;03:00
```

Each line requests one output file. Different ranges of the same video are allowed; duplicates
are detected by normalized video URL and range (`90` and `01:30` are equivalent). Invalid lines
are reviewed before import. Ranges outside the video duration, and ranges for videos with an
unknown duration, fail individually without stopping the remaining queue.

Cuts use yt-dlp's `--download-sections` and FFmpeg without forcing keyframes or additional
recoding for the cut. **Fast cuts may differ from the requested times due to keyframes.**
The existing MP4 conversion may still recode incompatible formats. Playlists always download
whole videos; range fields are disabled for playlists and TXT imports (TXT ranges come from
the file). If an ambiguous link is resolved as a playlist, clear any entered times before starting.

## Development

Python 3.11+:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt -e ".[dev]"
python -m youtube_smart_downloader
pytest -q
ruff check .
ruff format --check .
python -m mypy
```

Build and check the Windows executable:

```powershell
python scripts/build_windows.py
python scripts/check_windows_exe.py
python scripts/smoke_windows.py
python scripts/package_release.py
```

The executable is written to `dist/YouTubeSmartDownloader.exe`. Its product name, author/CompanyName (`ipeidro`), description, copyright, internal/original filename, project/support links and versions are generated from `pyproject.toml`. Both numeric and readable PE versions are validated against the runtime version.

The build embeds and copies license, privacy and uninstallation documents. It collects installed third-party license texts without a network request. The startup smoke test creates a hidden UI, runs the event loop and checks CustomTkinter resources. It does not install/update tools, query update services, download videos or save preferences. Packaging adds a portable ZIP and SHA-256 hashes of the final executable and ZIP.

The blue/cyan video-and-audio icon is shared by the window and executable. Its source and export instructions are in [assets/README.md](assets/README.md).

Close the executable before rebuilding it. To leave an existing instance running, build and test a separate copy:

```powershell
python scripts/build_windows.py --dist-dir dist/preview
python scripts/smoke_windows.py --executable dist/preview/YouTubeSmartDownloader.exe
```

The integration tests in `tests/test_local_media.py` require yt-dlp, FFmpeg and ffprobe on PATH. They serve synthetic media on `127.0.0.1`, check the decoded audio and test HTTP range resumption without contacting YouTube. They are skipped if the tools are unavailable.

## Audio-language guarantees

Language verification refers to extractor metadata, not speech recognition. `es-ES` requires that exact regional tag; generic `es` cannot prove that a track is from Spain. Original audio uses an explicit extractor marker when available; otherwise the choice is unverified. A fallback never verifies the originally requested language.

Only independent video and audio streams are used. Combined-only formats are skipped to avoid changing the selected audio silently. The download uses a snapshot of the inspected metadata and exactly the chosen tracks. If signed media URLs expire, retry to obtain new metadata. Active live streams are not supported.

## Files and resumption

- `.ytsd-archive.txt` records provider and video ID in yt-dlp-compatible format. The application updates it atomically after validating and publishing the MP4. Only YouTube is supported. An archived ID represents a video, not an audio/quality variant; use a separate destination for another variant. Existing archive entries are respected without certifying old files or their language.
- `.ytsd-clips.txt` separately records video IDs and normalized ranges after successful validation and publication. Whole-video entries do not skip clips, and clips do not skip whole videos. Clip filenames and temporary-work identities include their range; the report records requested start/end seconds. Clip archive entries also do not distinguish audio/quality variants. Cuts are verified against the requested clip duration with a tolerance of the greater of two seconds or 5%.
- **Create a subfolder** applies to every input: the video title, playlist title or TXT filename without its extension determines the folder name. Names are sanitized for Windows. When unchecked, all files go directly into the selected destination. Playlist and TXT entries do not get additional per-video subfolders.
- `.ytsd-work` holds partial files and metadata snapshots, identified by video and selected tracks. Retry with the same destination and track selection. Queue-index changes do not move the partial files. When subfolders are enabled, a changed video/playlist title or TXT filename changes the destination; select the previous folder and disable automatic subfolders to reuse its partials. Partial files from older versions that did not create video/TXT subfolders remain in their original location.
- Metadata snapshots contain media URLs and are deleted with the work directory after success. Interrupted jobs keep them locally.
- ffprobe checks the container, one video stream, exactly one audio stream and duration before publication. Existing destination files are never overwritten. Invalid staged MP4 files are regenerated. This check does not replace full decoding or listening to the audio.
- Each session keeps a JSON report in `.ytsd-reports`; `download-report.json` is the latest session. Reports distinguish new downloads, archived videos, skips, failures and cancellation. Older `informe-descarga.json` reports are left untouched.
- Technical `video_format` and `audio_format` IDs remain available for diagnostics; additional details describe codecs, resolution, FPS, language, bitrate and channels where metadata provides them.

## Tool checks and updates

Local checks execute each tool's version command with a timeout. Update checks run in the background, use a short-lived local cache, and query only the three relevant winget packages. Package metadata is not proof that an unrelated executable earlier on PATH was updated. Manually installed or unrecognized versions are reported as having unknown update status; working local tools remain usable. Installation and updates always require confirmation and affect only the listed packages.

## CI and releases

Pull request commits run Ruff, mypy, the full test suite and a Windows build/startup check. Windows tests cover Python 3.11, 3.12 and 3.13; a secondary Linux run covers Python 3.12 on the explicit `ubuntu-24.04` image. GitHub JavaScript actions use Node.js 24; that runtime belongs to CI and is not an application dependency. CI installs yt-dlp and FFmpeg/ffprobe and verifies their presence so the offline media integration tests are exercised rather than silently skipped. `requirements-ci.txt` pins the CI media test dependency alongside the development toolchain.

A push to `main`, including a merge, validates the integrated code and generates its executable artifact. Feature-branch push runs are omitted to avoid duplicating PR checks. Approval alone does not publish a release or merge code. Tags matching `v*` must agree with both package version declarations and reference a commit integrated into `main`. The release workflow reuses the complete CI workflow and publishes its tested Windows artifact only after all jobs succeed. No tag or release is created automatically by merging a PR. The same build/startup scripts are used locally and in CI. `requirements-dev.txt` pins the validated Python toolchain.


## Architecture

- `core.py`: pure language, quality and download argument policies.
- `inputs.py`: input classification and TXT validation.
- `engine.py`: queue planning, metadata and download orchestration.
- `processes.py`: cancellable subprocess execution.
- `tools.py`: local dependency checks, winget update discovery and maintenance.
- `storage.py`: atomic reports, archive and output publication.
- `app.py`: English CustomTkinter UI and worker/event coordination.
- `settings.py`: local preferences under `%APPDATA%/YouTubeSmartDownloader`.

See [LIMITATIONS.md](docs/LIMITATIONS.md) for remaining limits and privacy details.

## Licenses and contribution

The application source is [MIT licensed](LICENSE), copyright (c) 2026 ipeidro. This project is not affiliated with YouTube or Google. [Third-party components](docs/THIRD_PARTY.md) retain their licenses; full installed license texts are embedded in the executable and included in the portable ZIP. External tools retain their own licenses: [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/legal.html) and [Deno](https://deno.com/). Review the conditions of the actual binaries before redistribution.

Report bugs with reproducible steps. Include tests for changes to audio selection and download behavior. Never commit credentials, session cookies or downloaded videos.
