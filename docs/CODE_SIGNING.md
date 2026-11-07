# Code signing policy

## Current status

SignPath integration is prepared but not activated. Acceptance by SignPath Foundation, account provisioning and certificate configuration are still pending. Existing releases, including v0.1.0, are unsigned. The presence of publisher metadata in an EXE does not constitute a digital signature.

If accepted, the intended attribution is: Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org). This is a planned arrangement, not a claim that sponsorship or a certificate has already been granted. Update this status after acceptance and before enabling production signing.

## Project ownership and responsibilities

Author and copyright holder: **ipeidro**.

| Role | Responsible account |
| --- | --- |
| Author and maintainer | [@ipeidro-source](https://github.com/ipeidro-source) |
| Committer and reviewer | [@ipeidro-source](https://github.com/ipeidro-source) |
| Signing approver | [@ipeidro-source](https://github.com/ipeidro-source) |

This is currently a single-maintainer project; these roles are not independent reviewers. External contributions require maintainer review. The maintainer confirmed that GitHub multi-factor authentication is enabled. Multi-factor authentication is also required for the SignPath account before activation. Do not share account credentials or API tokens.

## Scope and approval

Only the project's `YouTubeSmartDownloader.exe`, built from this public repository on GitHub-hosted runners, may be submitted for signing. Dependency binaries are not separately re-signed with the project's certificate. yt-dlp, FFmpeg, ffprobe and Deno remain external and are not included in the application artifact.

Every production signing request requires manual approval in SignPath. Before approval, check the tag, commit, CI results, source changes, dependency changes and the uploaded artifact's identity. A PR approval, merge or pushed tag does not approve a signature. Do not approve unexpected requests.

Release tags must match the project and runtime versions and reference a commit integrated into `main`. CI tests the unsigned binary before submission. Once signing is enabled, publication requires a valid Authenticode signature from the configured certificate subject, a timestamp, matching PE metadata, and a successful startup check of the signed binary. A signing rejection, timeout, invalid signature or failed check prevents publication; there is no unsigned fallback when signing is enabled.

## Privacy and system changes

See the [privacy policy](PRIVACY.md), [uninstallation instructions](UNINSTALL.md) and [third-party components](THIRD_PARTY.md). Startup may contact winget sources automatically to check tool updates. Download URLs are sent to the services used by yt-dlp after a user starts a download. Installation and updates require confirmation and identify the affected packages. The application has no backend or telemetry.

## Verification and reporting

Download only from the project's [releases page](https://github.com/ipeidro-source/youtube-smart-downloader/releases). For a release advertised as signed, inspect Properties > Digital Signatures, or run:

```powershell
Get-AuthenticodeSignature -LiteralPath .\YouTubeSmartDownloader.exe |
    Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
Get-FileHash -LiteralPath .\YouTubeSmartDownloader.exe -Algorithm SHA256
```

Compare the hash with `SHA256SUMS.txt` from the same release. A hash confirms that files match; it does not replace certificate validation. The certificate subject is assigned by SignPath Foundation; it may name the Foundation rather than the author. `CompanyName=ipeidro` is descriptive file metadata, not the certificate identity. Signing does not guarantee the immediate disappearance of SmartScreen warnings.

Report suspected tampering through [GitHub Issues](https://github.com/ipeidro-source/youtube-smart-downloader/issues), including the release URL, hash and signature status. Never attach credentials, cookies or private media URLs. Signing requests must be stopped while a suspected compromise is investigated.
