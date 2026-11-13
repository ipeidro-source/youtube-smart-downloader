# Privacy policy

YouTube Smart Downloader is maintained by **ipeidro**, GitHub account [@ipeidro-source](https://github.com/ipeidro-source). Contact and support are available through [GitHub Issues](https://github.com/ipeidro-source/youtube-smart-downloader/issues). Do not post personal data, cookies, credentials or signed media URLs in public issues.

## Application data

The application has no account system, application backend, advertising or telemetry. Preferences and tool-update cache files are stored locally under `%APPDATA%\YouTubeSmartDownloader`. Downloaded media, reports, archives and resumable work files are stored in the destination selected by the user.

Local logs and reports can contain video URLs, IDs, titles, selected formats, filesystem paths and error messages. Interrupted download metadata may contain temporary signed media URLs; successful downloads remove their work files. These files are not uploaded to the maintainer. The application does not intentionally store passwords, authentication cookies or API keys, and ignores global yt-dlp configuration.

## Network connections

- At startup, the application checks installed tool versions and available impersonation profiles locally and may automatically query the configured winget source for newer versions. Its short-lived cache can avoid a new query. These checks do not send the download URL to the maintainer.
- When the user starts a download, yt-dlp contacts YouTube and the related extraction, media-delivery and supporting services it requires. Those services receive the requested URLs and normal network information, such as the public IP address.
- Installing or updating tools, after confirmation, contacts winget and the package distribution services. The affected packages are yt-dlp, FFmpeg (including ffprobe) and Deno. These operations may modify PATH or request Windows elevation through their installers.
- If the user downloads the application or reports an issue on GitHub, GitHub processes those interactions. Windows may separately contact certificate-validation, SmartScreen or other security services according to the operating system's settings.

Third-party policies apply to those services: [Google/YouTube](https://policies.google.com/privacy), [Microsoft/winget](https://privacy.microsoft.com/privacystatement), [GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org) and [Deno](https://deno.com/privacy). Package download hosts are selected by the relevant winget manifest or upstream tool and may change.

Browser impersonation changes the network connection characteristics yt-dlp presents to the destination service. It does not import a browser account, personal profile, cookies or browsing history. The chosen browser family is stored in local preferences and session reports.

## Control and deletion

You can decline tool installation or updates, install tools manually, or use working tools when an update query fails. Current releases do not expose a separate switch to disable startup update discovery. Network access is required for online downloads.

Use the [uninstallation instructions](UNINSTALL.md) to remove preferences, caches and the executable. Downloaded files remain under your control. Deleting partial work files prevents their resumption; deleting archives removes the record used to avoid repeat downloads. No server-side application account or maintainer-held user dataset exists to delete.
