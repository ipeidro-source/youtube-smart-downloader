# Uninstallation

## Portable application

1. Cancel active work and close YouTube Smart Downloader. Wait for any tool installation or update to finish.
2. Delete `YouTubeSmartDownloader.exe` and any extracted release documents or shortcuts you created. There is no application installer, Windows service, scheduled task or autorun entry to remove.
3. To remove preferences and the update cache, open `%APPDATA%` in File Explorer and delete only the `YouTubeSmartDownloader` folder. Keep it if you want to preserve preferences for a later version.
4. Downloaded videos are not deleted automatically. In your chosen download destination, you may separately remove `.ytsd-work`, `.ytsd-reports`, `.ytsd-archive.txt`, `.ytsd-clips.txt` and `download-report.json` if you no longer need them. Partial downloads cannot resume after deleting their work files. Removing the corresponding whole-video or clip archive allows those downloads again. These files may also be inside automatically created source subfolders. Preserve any media or reports you want to keep.

## External tools

yt-dlp, FFmpeg/ffprobe and Deno are separate programs and may be shared with other applications. Removing the downloader does not remove them. Uninstall them only if you no longer need them elsewhere.

If installed through this application's winget maintenance, inspect the exact packages first:

```powershell
winget list --id yt-dlp.yt-dlp --exact
winget list --id yt-dlp.FFmpeg --exact
winget list --id DenoLand.Deno --exact
```

To remove a package that you have decided is no longer needed, run its corresponding command:

```powershell
winget uninstall --id yt-dlp.yt-dlp --exact
winget uninstall --id yt-dlp.FFmpeg --exact
winget uninstall --id DenoLand.Deno --exact
```

FFmpeg and ffprobe belong to the same package. If a tool was installed manually or through another package manager, use that installation method's uninstaller instead. Restart open terminals and applications after changes to PATH. Do not remove unrelated packages or whole PATH entries without checking their ownership.
