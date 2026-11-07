"""English-language, Windows desktop GUI."""

from __future__ import annotations

import queue
import argparse
import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from .core import LANGUAGES, Preferences
from .inputs import classify_url, parse_text_links
from .engine import Cancelled, DownloadEngine
from .settings import load, save
from .tools import SPECS, ToolManager, ToolStatus


class App(ctk.CTk):
    def __init__(self, *, hidden: bool = False) -> None:
        super().__init__()
        if hidden:
            self.withdraw()
        self.closing = False
        self.tools_ready = False
        self.tool_statuses: list[ToolStatus] = []
        self.check_event = threading.Event()
        self.check_worker: threading.Thread | None = None
        self.title("YouTube Smart Downloader")
        icon_directory = Path(__file__).with_name("assets")
        self._app_icon = tk.PhotoImage(file=str(icon_directory / "app-icon.png"))
        self.iconphoto(True, self._app_icon)
        if os.name == "nt":
            self.iconbitmap(str(icon_directory / "app-icon.ico"))
        self.geometry("760x720")
        self.minsize(650, 650)
        ctk.set_appearance_mode("System")
        data = load()
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.engine: DownloadEngine | None = None
        self.url = tk.StringVar(value="")
        self.destination = tk.StringVar(
            value=str(data.get("destination") or Path.home() / "Downloads")
        )
        self.imported_links: list[str] = []
        self.imported_name: str | None = None
        self.language = tk.StringVar(value=str(data.get("language") or "es"))
        self.missing = tk.StringVar(value=str(data.get("missing") or "skip"))
        self.quality = tk.StringVar(value=str(data.get("quality") or "best"))
        self.subfolder = tk.BooleanVar(value=bool(data.get("playlist_subfolder", True)))
        self._build()
        self.url.trace_add("write", self._input_changed)
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.start_button.configure(state="disabled")
        if not hidden:
            self.after(200, self._begin_tool_check)

    def _build(self) -> None:
        container = ctk.CTkFrame(self, corner_radius=0)
        container.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            container, text="YouTube Smart Downloader", font=ctk.CTkFont(size=25, weight="bold")
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(container, text="YouTube link").pack(anchor="w")
        source_row = ctk.CTkFrame(container, fg_color="transparent")
        source_row.pack(fill="x", pady=(5, 4))
        ctk.CTkEntry(
            source_row, textvariable=self.url, placeholder_text="https://www.youtube.com/..."
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.import_button = ctk.CTkButton(
            source_row, text="Import links...", width=120, command=self._import_links
        )
        self.import_button.pack(side="right")
        self.input_label = ctk.CTkLabel(
            container, text="Paste a video or playlist link, or import a TXT file."
        )
        self.input_label.pack(anchor="w", pady=(0, 12))
        ctk.CTkLabel(container, text="Destination folder").pack(anchor="w")
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=(5, 14))
        ctk.CTkEntry(row, textvariable=self.destination).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(row, text="Browse…", width=100, command=self._browse).pack(side="right")
        ctk.CTkCheckBox(
            container,
            text="Create a subfolder named after the video, playlist or TXT file",
            variable=self.subfolder,
        ).pack(anchor="w", pady=(0, 14))
        grid = ctk.CTkFrame(container, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(grid, text="Audio language").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(grid, text="Maximum quality").grid(row=0, column=1, sticky="w")
        languages = list(LANGUAGES.values())
        initial_language = LANGUAGES.get(self.language.get(), LANGUAGES["es"])
        self.language_menu = ctk.CTkOptionMenu(
            grid, values=languages, command=self._language_changed
        )
        self.language_menu.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(5, 14))
        self.language_menu.set(initial_language)
        self.quality_menu = ctk.CTkOptionMenu(
            grid,
            values=["Best available", "1080p", "720p", "480p"],
            command=self._quality_changed,
        )
        self.quality_menu.grid(row=1, column=1, sticky="ew", pady=(5, 14))
        self.quality_menu.set(
            {"best": "Best available", "1080": "1080p", "720": "720p", "480": "480p"}.get(
                self.quality.get(), "Best available"
            )
        )
        ctk.CTkLabel(container, text="If this language is unavailable:").pack(anchor="w")
        ctk.CTkRadioButton(
            container,
            text="Skip the video and report it (recommended)",
            variable=self.missing,
            value="skip",
        ).pack(anchor="w", pady=(5, 5))
        ctk.CTkRadioButton(
            container,
            text="Use original/default audio as a fallback",
            variable=self.missing,
            value="fallback",
        ).pack(anchor="w", pady=(0, 15))
        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 15))
        self.start_button = ctk.CTkButton(actions, text="Download", command=self._start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ctk.CTkButton(
            actions, text="Cancel", state="disabled", fg_color="gray", command=self._cancel
        )
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.install_button = ctk.CTkButton(
            actions, text="Update tools", fg_color="#555", command=self._install
        )
        self.bar = ctk.CTkProgressBar(container)
        self.bar.pack(fill="x")
        self.bar.set(0)
        self.status_label = ctk.CTkLabel(container, text="Ready", wraplength=650, justify="left")
        self.status_label.pack(anchor="w", pady=(9, 6))
        self.log = ctk.CTkTextbox(container, height=115)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    def _begin_tool_check(self) -> None:
        if self.closing:
            return
        if self.check_worker and self.check_worker.is_alive():
            self.after(100, self._begin_tool_check)
            return
        self.check_event = threading.Event()
        manager = ToolManager(self.check_event)
        self.status_label.configure(text="Checking required tools...")

        def check() -> None:
            try:
                statuses = manager.probe()
                self.events.put(("tools_local", statuses))
                if all(status.usable for status in statuses):
                    self.events.put(("tools_updates", manager.check_updates(statuses)))
            except Cancelled:
                pass
            except Exception as exc:
                self.events.put(("tools_check_error", str(exc)))

        self.check_worker = threading.Thread(target=check)
        self.check_worker.start()

    def _tools_local(self, statuses: list[ToolStatus]) -> None:
        self.tool_statuses = statuses
        self.tools_ready = all(status.usable for status in statuses)
        self._set_busy(bool(self.worker and self.worker.is_alive()))
        if self.closing:
            return
        for status in statuses:
            self._log(f"{status.spec.name}: {status.version or status.error}")
        if self.tools_ready:
            self.status_label.configure(text="Ready; checking for tool updates...")
            return
        self.install_button.pack_forget()
        missing = [status for status in statuses if not status.usable]
        details = "\n".join(f"- {s.spec.name}: {s.spec.description}\n  {s.error}" for s in missing)
        self.status_label.configure(text="Required tools are missing or unusable")
        if messagebox.askyesno(
            "Required tools",
            "Downloads require these tools:\n\n"
            + details
            + "\n\nInstall or repair them using winget?\nChoose No to exit. If you just installed them, restart the app first.",
        ):
            self._install(install=True)
        else:
            self._close()

    def _tools_updates(self, statuses: list[ToolStatus]) -> None:
        self.tool_statuses = statuses
        available = [s for s in statuses if s.update == "available"]
        if available:
            self.install_button.pack(side="left")
        else:
            self.install_button.pack_forget()
        for status in statuses:
            self._log(f"{status.spec.name}: {status.update_message}")
        busy = bool(self.worker and self.worker.is_alive())
        self._set_busy(busy)
        if not busy:
            self.status_label.configure(
                text="Ready"
                if all(s.update == "current" for s in statuses)
                else "Ready; updates available"
                if available
                else "Ready; update status could not be verified"
            )

    def _input_changed(self, *_args: str) -> None:
        self.imported_links = []
        self.imported_name = None
        try:
            source = classify_url(self.url.get())
            label = {
                "video": "Video detected",
                "playlist": "Playlist detected",
                "ambiguous": "Video and playlist detected; you will choose before downloading",
            }[source.kind]
        except ValueError:
            label = "Paste a video or playlist link, or import a TXT file."
        self.input_label.configure(text=label)

    def _import_links(self) -> None:
        filename = filedialog.askopenfilename(
            title="Import video links", filetypes=[("UTF-8 text files", "*.txt")]
        )
        if not filename:
            return
        try:
            imported = parse_text_links(Path(filename).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("Import failed", f"Could not read the UTF-8 file.\n{exc}")
            return
        problems = imported.issues + imported.duplicates
        for problem in problems:
            self._log(problem)
        if not imported.links:
            messagebox.showerror(
                "Import failed",
                "No valid individual video links were found.\n" + "\n".join(problems[:8]),
            )
            return
        if problems and not messagebox.askyesno(
            "Review import",
            f"Found {len(imported.links)} unique video links, {len(imported.issues)} invalid lines and {len(imported.duplicates)} duplicates.\n\n"
            + "\n".join(problems[:8])
            + "\n\nImport only the valid unique links? Full details are in the log.",
        ):
            return
        self.url.set(f"TXT: {Path(filename).name}")
        self.imported_links = imported.links
        self.imported_name = Path(filename).stem
        self.input_label.configure(text=f"Imported {len(imported.links)} videos in file order")

    def _language_changed(self, value: str) -> None:
        self.language.set(next(key for key, label in LANGUAGES.items() if label == value))

    def _quality_changed(self, value: str) -> None:
        self.quality.set(
            {"Best available": "best", "1080p": "1080", "720p": "720", "480p": "480"}[value]
        )

    def _browse(self) -> None:
        path = filedialog.askdirectory(initialdir=self.destination.get())
        if path:
            self.destination.set(path)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _save(self) -> None:
        try:
            save(
                {
                    "destination": self.destination.get(),
                    "language": self.language.get(),
                    "missing": self.missing.get(),
                    "quality": self.quality.get(),
                    "playlist_subfolder": self.subfolder.get(),
                }
            )
        except OSError as exc:
            self._log(f"Could not save preferences: {exc}")
            messagebox.showwarning("Preferences", f"Could not save preferences.\n{exc}")

    def _set_busy(self, busy: bool) -> None:
        if self.closing:
            return
        self.start_button.configure(state="normal" if not busy and self.tools_ready else "disabled")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.install_button.configure(state="disabled" if busy else "normal")
        self.import_button.configure(state="disabled" if busy else "normal")

    def _start(self) -> None:
        if not self.tools_ready or (self.worker and self.worker.is_alive()):
            return
        url: str | list[str]
        batch_name: str | None = None
        is_playlist = False
        if self.imported_links:
            url = self.imported_links.copy()
            batch_name = self.imported_name
        else:
            try:
                source = classify_url(self.url.get().strip())
            except ValueError as exc:
                messagebox.showerror("Invalid link", str(exc))
                return
            if source.kind == "ambiguous":
                choice = messagebox.askyesnocancel(
                    "Video or playlist?",
                    "This link contains both a video and a playlist.\n\nYes: download the entire playlist.\nNo: download only this video.\nCancel: go back.",
                )
                if choice is None:
                    return
                is_playlist = choice
            else:
                is_playlist = source.kind == "playlist"
            url = source.playlist_url if is_playlist else source.video_url
        folder = Path(self.destination.get().strip()).expanduser()
        if not str(self.destination.get()).strip():
            messagebox.showerror("Folder", "Choose a destination folder.")
            return
        prefs = Preferences(
            self.language.get(), self.missing.get(), self.quality.get(), self.subfolder.get()
        )
        try:
            prefs.validate()
        except ValueError as exc:
            messagebox.showerror("Preferences", str(exc))
            return
        self._save()
        self.bar.set(0)
        self._set_busy(True)
        engine = DownloadEngine(
            lambda s: self.events.put(("status", s)),
            lambda n, t, p: self.events.put(("progress", n, t, p)),
        )
        self.engine = engine

        def work() -> None:
            try:
                result = engine.download(url, folder, is_playlist, prefs, batch_name=batch_name)
                self.events.put(("done", result))
            except Cancelled:
                self.events.put(("stopped", engine.report))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker = threading.Thread(target=work)
        self.worker.start()

    def _cancel(self) -> None:
        if self.engine:
            self.engine.cancel()
            self.cancel_button.configure(state="disabled")
            self._log("Cancellation requested.")

    def _install(self, *, install: bool = False) -> None:
        if self.worker and self.worker.is_alive():
            return
        statuses = self.tool_statuses.copy()
        if not install:
            available = {
                s.spec.package: s.available_version for s in statuses if s.update == "available"
            }
            if not available:
                return
            details = "\n".join(f"- {package}: {version}" for package, version in available.items())
            if not messagebox.askyesno(
                "Update tools",
                "Update only these packages using winget?\n\n"
                + details
                + "\n\nYou can keep using the installed versions by choosing No.",
            ):
                return
        self.check_event.set()
        self.tools_ready = False
        self._set_busy(True)
        engine = DownloadEngine(lambda s: self.events.put(("status", s)), lambda *_: None)
        self.engine = engine

        def work() -> None:
            try:
                if self.check_worker:
                    self.check_worker.join()
                manager = ToolManager(engine.cancel_event)
                manager.maintain(
                    statuses, lambda s: self.events.put(("status", s)), update=not install
                )
                self.events.put(("installed",))
            except Cancelled:
                self.events.put(("stopped", None))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker = threading.Thread(target=work)
        self.worker.start()

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "tools_local":
                    if not self.closing:
                        self._tools_local(event[1])
                elif kind == "tools_updates":
                    if not self.closing:
                        self._tools_updates(event[1])
                elif kind == "tools_check_error":
                    self._log("Tool check failed: " + event[1])
                    if self.tools_ready and not (self.worker and self.worker.is_alive()):
                        self.status_label.configure(
                            text="Ready; update status could not be verified"
                        )
                    if not self.tools_ready and not self.closing:
                        if messagebox.askretrycancel("Tool check failed", event[1]):
                            self._begin_tool_check()
                        else:
                            self._close()
                elif kind == "status":
                    self.status_label.configure(text=event[1][:160])
                    self._log(event[1])
                elif kind == "progress":
                    _, n, total, percentage = event
                    try:
                        ratio = float(percentage.rstrip("%")) / 100
                    except ValueError:
                        ratio = 0
                    self.bar.set(min(1, max(0, (n - 1 + ratio) / total)))
                elif kind == "done":
                    report = event[1]
                    self._set_busy(False)
                    self.bar.set(1)
                    summary = f"Completed: {len(report['downloaded'])} downloaded; {len(report['archived'])} already archived; {len(report['omitted'])} skipped; {len(report['failed'])} errors.\nReport: {report['report_path']}"
                    self._log(summary)
                    self.status_label.configure(
                        text="Finished with errors" if report["failed"] else "Finished"
                    )
                    if not self.closing:
                        messagebox.showinfo("Download report", summary)
                elif kind == "stopped":
                    self._set_busy(False)
                    report = event[1]
                    self.status_label.configure(text="Operation cancelled")
                    self._log("Operation cancelled. Available partial files have been kept.")
                    if report:
                        self._log(f"Partial report: {report['report_path']}")
                    elif not self.closing:
                        self._begin_tool_check()
                elif kind == "installed":
                    self._set_busy(False)
                    if not self.closing:
                        messagebox.showinfo(
                            "Tool maintenance",
                            "Finished. The app will recheck tools. Restart it if Windows PATH has changed.",
                        )
                        self._begin_tool_check()
                elif kind == "error":
                    self._set_busy(False)
                    self._log(event[1])
                    self.status_label.configure(text="Error")
                    if self.engine and self.engine.report:
                        self._log(f"Report: {self.engine.report['report_path']}")
                    if not self.closing:
                        messagebox.showerror("Error", event[1][:700])
                        if not self.tools_ready:
                            self._begin_tool_check()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _close(self) -> None:
        if self.closing:
            return
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Close", "An operation is running. Cancel it and close?"):
                return
        self._save()
        self.closing = True
        self.start_button.configure(state="disabled")
        self.install_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.import_button.configure(state="disabled")
        self.check_event.set()
        if self.engine:
            self.engine.cancel()
        self.status_label.configure(text="Closing; waiting for child processes…")
        self._finish_close()

    def _finish_close(self) -> None:
        if (self.worker and self.worker.is_alive()) or (
            self.check_worker and self.check_worker.is_alive()
        ):
            self.after(100, self._finish_close)
            return
        self.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Smart Downloader")
    parser.add_argument("--smoke-test", type=Path, metavar="RESULT_JSON", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = App(hidden=args.smoke_test is not None)
    if args.smoke_test is not None:
        # Exercise real Tk/CTk initialization and the event loop in the frozen executable.
        def finish_smoke() -> None:
            statuses = [
                ToolStatus(spec, path="smoke-test", version="test", update="current")
                for spec in SPECS
            ]
            app._tools_local(statuses)
            app._tools_updates(statuses)
            assert app.tools_ready and app.start_button.cget("state") == "normal"
            assert not app.install_button.winfo_manager()
            app.url.set("https://www.youtube.com/watch?v=abcdefghijk&list=PL_test")
            assert "Video and playlist" in app.input_label.cget("text")
            assert app._app_icon.width() == 256
            assert (Path(__file__).with_name("assets") / "app-icon.ico").is_file()
            args.smoke_test.write_text(
                json.dumps({"status": "ok", "title": app.title()}), encoding="utf-8"
            )
            app.destroy()

        app.after(300, finish_smoke)
    app.mainloop()


if __name__ == "__main__":
    main()
