# Limitations and privacy

## Platform and dependencies

Windows is the supported desktop platform. Linux CI validates shared logic, not a supported Linux desktop distribution. The Windows executable is portable. It does not bundle yt-dlp, FFmpeg/ffprobe or Deno.

winget is required only for automatic maintenance. Working manually installed tools remain usable, but their update status may be unknown. Package catalogs may lag upstream releases. Query failures and unknown versions must not be reported as up to date. Update discovery uses timeouts and a cache; offline users can continue with working local tools.

Cancelling installation stops the tracked process tree when Windows permits it. Already installed packages remain installed, and a separate elevated installer or Windows Installer service may continue. Recheck tool availability after interruption. Restart the application if PATH changed.

## Language and media

Language labels are metadata, not recognition of the spoken language. Incorrect upstream labels cannot be detected reliably. Regional Spanish requires an explicit tag. Fallback tracks are unverified for the requested language. Original-track detection is limited to explicit extractor markers.

Multiple requested languages may not all be available. Missing tracks are reported; failures downloading an available selected track fail the video. Subtitles are embedded, and their availability and automatic-caption quality depend on YouTube. MKV subtitles are non-default; MP4 enables the first subtitle for player selection even when its default disposition is cleared. Player preferences can still enable subtitles automatically. Compatible streams are copied; MP4 may require H.264/AAC conversion for unsupported codecs.

Combined-only video/audio formats and active live streams are not downloaded. ffprobe checks structure, stream counts and duration; it cannot prove every frame is decodable or that the voice matches the selected language. Unknown format details are shown as unknown instead of inferred from technical IDs.

Automatic impersonation leaves the decision to yt-dlp. Forced browser families require support in the installed yt-dlp; unavailable choices fail before extraction. Profiles are detected locally and are not personal browser profiles. Forcing a profile may reduce speed or stability and does not bypass account requirements.

## Inputs and resumption

Video/playlist links are ambiguous when both identifiers are present; users choose the intended scope. TXT imports accept individual YouTube video links only. Invalid lines and duplicates require review before proceeding.

Older partial files are not migrated into `.ytsd-work`. Resumption requires the same destination and compatible track identifiers/metadata. When automatic subfolders are enabled, changes to the video title, playlist title or TXT filename change the destination. Choose the previous folder and disable subfolders to reuse files already there. Expired media URLs require a retry with fresh metadata.

The archive records one entry per provider/video ID, not per audio/subtitle selection, container or quality. It does not verify that an old file is still present or complete. Use separate destinations for different variants. Avoid concurrent application instances writing to one destination: output files are protected against overwrite, but the archive does not implement an interprocess lock.

Reports are incremental and session-specific. Insufficient disk space or permissions can prevent persistence; the UI reports these errors. Existing reports and preferences remain local and are not rewritten merely to translate them.

## Privacy

There is no application backend, account system or telemetry. YouTube URLs are sent to the services used by yt-dlp. Tool update queries contact winget sources. URLs, titles and signed media URLs may appear in local reports, logs and work files. No cookies, passwords or API keys are intentionally stored. Global yt-dlp configuration is ignored to preserve application policy.

Startup update queries may run automatically; the application currently has no separate opt-out switch. The full [privacy policy](PRIVACY.md) describes network activity, third-party services, local storage and deletion. [Uninstallation](UNINSTALL.md) includes optional removal of separately installed tools.

Only known YouTube HTTP(S) hosts are accepted. This validation is not an execution sandbox. Download content only when you have permission or the necessary rights.

## Future work

- More extractor fixtures and original-audio evidence.
- An actual installer.
- Better handling of changed playlists and archived files moved by the user.
- An interprocess destination lock.
