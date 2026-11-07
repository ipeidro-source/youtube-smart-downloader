# SignPath application and activation

## Application information

| Field | Prepared value |
| --- | --- |
| Project | YouTube Smart Downloader |
| Maintainer / author | ipeidro |
| GitHub account | https://github.com/ipeidro-source |
| Repository / website | https://github.com/ipeidro-source/youtube-smart-downloader |
| Public contact / support | https://github.com/ipeidro-source/youtube-smart-downloader/issues |
| Source license | MIT |
| Current published release | v0.1.0; unsigned |
| Proposed next release | v0.1.1; do not recreate the existing v0.1.0 tag |
| Artifact to sign | YouTubeSmartDownloader.exe, Windows x64, PyInstaller onefile |
| Build environment | GitHub Actions, GitHub-hosted Windows runner, Python 3.12 |
| Committer, reviewer, approver | @ipeidro-source (one maintainer) |
| Signing policy | [Code signing policy](CODE_SIGNING.md) |
| Privacy | [Privacy policy](PRIVACY.md) |
| Removal | [Uninstallation](UNINSTALL.md) |

Suggested project description:

> Free, MIT-licensed Windows desktop application built with Python and CustomTkinter. It downloads YouTube videos and playlists, imports lists of video links, and explicitly selects audio-language tracks using yt-dlp. It supports cancellation, resumable partial files and local download reports. yt-dlp, FFmpeg/ffprobe and Deno are external dependencies; they are not bundled or signed with the application. Users confirm installation and updates through winget. The application has no backend, account system or telemetry. Startup may query winget sources for tool updates.

The repository was first published on 7 November 2026 and is still new. Explain that history honestly; do not claim established reputation or guaranteed eligibility. SignPath decides whether to accept the project. The maintainer's public name is `ipeidro`. Use the private email address supplied separately by the maintainer as the application's contact address, so SignPath can communicate about the request and account onboarding. Do not put that address in this document, the EXE or the PR. Supply any additional private or legal identity information requested directly to SignPath. The public support URL above is for users, not a substitute for the private application contact.

## Before applying

1. Merge the reviewed preparation PR after all CI checks pass, so the policy and metadata are visible on `main`.
2. Review [SignPath Foundation's current conditions](https://signpath.org/terms). Ensure the public code signing policy accurately names the sole maintainer and responsibilities.
3. Review generated notices, privacy, uninstallation and the proposed executable metadata. GitHub MFA has been confirmed by the maintainer; enable SignPath MFA when the account is provisioned.
4. Apply at https://signpath.org/apply. No request has been submitted by this repository's preparation work. Acceptance, account access and a production certificate are external prerequisites.

## After acceptance

1. Update the status/attribution in `CODE_SIGNING.md` through a PR to record the actual accepted arrangement. Do not imply sponsorship before acceptance.
2. Configure the GitHub.com trusted build system for this repository in SignPath. Install its GitHub App with access limited to this repository if required by its setup. Use only GitHub-hosted runners for the full build chain.
3. Configure a production signing policy with @ipeidro-source as manual approver and mandatory origin verification, restricted to this repository and release tags integrated into `main`. Never grant PR jobs signing credentials.
4. Import `.github/signpath/artifact-configuration.xml`. It signs only the outer application executable, enforces product/company/copyright/name/version fields and uses SHA-256. Do not add wildcards to sign upstream DLLs or external tools. Configure a trusted timestamp in SignPath; publication requires one.
5. Add the repository configuration listed below. Obtain the exact certificate subject from the accepted production certificate, including its formatting; do not assume it equals `ipeidro`.
6. Set `SIGNPATH_ENABLED=true` only after the account, manual approval policy, origin verification, certificate and timestamp are ready. Before activation, tag releases intentionally remain unsigned. After activation, a signature failure blocks publication.
7. Push a new matching version tag after merging. Review and approve the request in SignPath within the workflow's 60-minute signing wait. Rejected or expired requests do not publish a release. A rerun is subject to SignPath origin/rerun policy and requires a fresh review.

| GitHub configuration | Kind | Value |
| --- | --- | --- |
| `SIGNPATH_ENABLED` | Repository variable | `false` or absent until setup; `true` activates mandatory signing |
| `SIGNPATH_ORGANIZATION_ID` | Repository variable | Organization ID supplied by SignPath |
| `SIGNPATH_PROJECT_SLUG` | Repository variable | Project slug configured in SignPath |
| `SIGNPATH_SIGNING_POLICY_SLUG` | Repository variable | Production policy slug with manual approval |
| `SIGNPATH_CERTIFICATE_SUBJECT` | Repository variable | Exact expected production certificate subject |
| `SIGNPATH_API_TOKEN` | Actions secret | Token scoped to submitting requests for this project/policy; never commit it |

## Release flow and validation

Tags are validated before invoking the reusable CI. All tests, Ruff, formatting and mypy must pass. CI builds the EXE, checks its PE metadata and embedded notices, tests startup, and uploads the complete unsigned distribution as a workflow artifact. The reusable workflow exposes that artifact ID to the signing job, preserving its GitHub provenance.

If enabled, SignPath signs that artifact after manual approval. A Windows job checks the signed EXE's trusted Authenticode status, exact configured subject, timestamp, unchanged product metadata, embedded documentation and startup. Publication then packages the signed artifact, without rebuilding it, into a portable ZIP and computes SHA-256 hashes of the final EXE and ZIP. If signing is not activated, publication explicitly describes the release as unsigned. Both paths link the code signing policy in the release notes.

The production signing path cannot be fully exercised until SignPath grants access and provisions the certificate. Local and PR checks validate metadata, notices, packaging, workflow configuration and ordinary unsigned startup. An EXE with correct CompanyName metadata alone will still show an unknown publisher in Windows.

Official references: [GitHub integration](https://docs.signpath.io/trusted-build-systems/github), [artifact metadata restrictions](https://docs.signpath.io/artifact-configuration/reference#file-metadata-restrictions), [SignPath terms](https://signpath.org/terms).
