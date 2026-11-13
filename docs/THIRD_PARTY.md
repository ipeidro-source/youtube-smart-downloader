# Third-party components and license notices

The application source and original project assets are MIT licensed, copyright (c) 2026 ipeidro. Upstream components retain their respective licenses. The build preserves their full installed license texts in `THIRD_PARTY_NOTICES.txt`, embeds that file and the application license inside the executable, and includes readable copies in the portable ZIP. `THIRD_PARTY_COMPONENTS.json` records the installed Python build inputs and versions; it is not a complete SBOM or an inventory of every dynamically loaded operating-system library.

## Components used in the Windows executable

| Component | License / notices | Role |
| --- | --- | --- |
| Python and standard library | PSF license and included third-party terms | Embedded interpreter; its complete Windows `LICENSE.txt` is copied from the build installation |
| Tcl/Tk | Tcl/Tk permissive license | Tkinter runtime, native list controls and language popup windows; installed Tk terms and the upstream Tcl terms are included |
| CustomTkinter | MIT | UI and shapes font; its installed `LICENSE` is authoritative despite the inconsistent `License` field in version 5.2.2's package metadata |
| Roboto Regular and Medium | Apache-2.0; copyright 2011 Google Inc. All Rights Reserved. | Fonts included by CustomTkinter; license also identified in the fonts' name tables |
| darkdetect | BSD-3-Clause | Theme detection |
| packaging | Apache-2.0 OR BSD-2-Clause | Version handling; both license alternatives are retained |
| Pillow and bundled native dependencies | MIT-CMU plus the full upstream wheel notices | Image support imported by CustomTkinter; the wheel's license includes its native libraries' terms |
| typing_extensions | PSF-2.0 | Compatibility helpers, where collected |
| PyInstaller bootloader and runtime hooks | GPL-2.0-or-later WITH Bootloader-exception | Packaging runtime; the complete license and distribution exception are retained |
| OpenSSL 3 | Apache-2.0 | Runtime libraries from the Python installation; upstream license retained |
| Microsoft Windows runtime libraries | Microsoft runtime distribution terms | System/runtime dependencies supplied with Windows or the official Python installation; not claimed as project-owned OSS |

Pillow's bundled FreeType code is used under the FreeType License option: portions of this software are copyright The FreeType Project (https://freetype.org). All rights reserved. Its other native-library notices remain in the complete Pillow wheel license. Python's distribution notices cover additional interpreter components, including libffi, compression and other standard-library dependencies.

This list is intentionally conservative: some listed modules may not be collected by every Python/PyInstaller version. The build does not infer permission from a package name alone and fails if required installed license files are absent. Changes to dependencies, fonts, interpreter versions or bundling require renewed review. Build only with a trusted Python installation and inspect the PyInstaller analysis for unexpected binaries before approving a release.

## Tools installed separately

The application does not bundle or re-sign [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg/ffprobe](https://ffmpeg.org/legal.html) or [Deno](https://github.com/denoland/deno). Their actual releases and optional dependencies have their own notices and licenses. Installation and updates are explicitly confirmed. Automatic update discovery can contact winget at startup; see [Privacy](PRIVACY.md).

## Sources of supplementary texts

- Roboto: https://github.com/googlefonts/roboto/blob/main/LICENSE (Apache-2.0; the same standard text is also distributed by packaging).
- Tcl 8.6: https://github.com/tcltk/tcl/blob/core-8-6-branch/license.terms.
- OpenSSL 3.0: https://github.com/openssl/openssl/blob/openssl-3.0/LICENSE.txt.
- Other texts are read directly from the installed package distributions and the Windows Python/Tk installation, without network access during the build.
