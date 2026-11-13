"""English-language, Windows desktop GUI."""

from __future__ import annotations

import queue
import argparse
import json
import os
import threading
import tkinter as tk
from pathlib import Path
from functools import partial
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from . import APP_NAME, __version__
from .about import AboutWindow
from .core import LANGUAGES, Preferences
from .languages import LANGUAGE_NAMES
from .language_picker import LanguagePicker
from .inputs import classify_url, parse_text_links
from .requests import DownloadRequest, parse_time_range
from .engine import Cancelled, DownloadEngine
from .settings import load, save
from .tools import SPECS, ToolManager, ToolStatus


def language_options(audio: bool) -> dict[str, str]:
    names = dict(LANGUAGE_NAMES)
    if audio:
        names.update({"original": LANGUAGES["original"], "auto": LANGUAGES["auto"]})
    return {
        f"{name} [{code}]": code for code, name in sorted(names.items(), key=lambda item: item[1])
    }


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
        self._about_window: AboutWindow | None = None
        self.title(APP_NAME)
        icon_directory = Path(__file__).with_name("assets")
        self._app_icon = tk.PhotoImage(file=str(icon_directory / "app-icon.png"))
        self.iconphoto(True, self._app_icon)
        if os.name == "nt":
            self.iconbitmap(str(icon_directory / "app-icon.ico"))
        self.geometry("840x700")
        self.minsize(780, 660)
        ctk.set_appearance_mode("System")
        data = load()
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.engine: DownloadEngine | None = None
        self.url = tk.StringVar(value="")
        self.range_start = tk.StringVar(value="")
        self.range_end = tk.StringVar(value="")
        self.destination = tk.StringVar(
            value=str(data.get("destination") or Path.home() / "Downloads")
        )
        self.imported_links: list[DownloadRequest] = []
        self.imported_name: str | None = None
        self.audio_languages = list(data["audio_languages"])
        self.subtitle_languages = list(data["subtitle_languages"])
        self.default_audio = tk.StringVar(value=data["default_audio"])
        self.automatic_subtitles = tk.BooleanVar(value=data["automatic_subtitles"])
        self.output_container = tk.StringVar(value=data["container"])
        self.impersonation = tk.StringVar(value=data["impersonation"])
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
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=14, pady=10)
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(header, text=APP_NAME, font=ctk.CTkFont(size=23, weight="bold")).pack(
            side="left"
        )
        ctk.CTkButton(header, text="About", width=70, command=self._show_about).pack(side="right")
        source_row = ctk.CTkFrame(main, fg_color="transparent")
        source_row.pack(fill="x")
        ctk.CTkEntry(
            source_row, textvariable=self.url, placeholder_text="YouTube video or playlist link"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.import_button = ctk.CTkButton(
            source_row, text="Import links...", width=120, command=self._import_links
        )
        self.import_button.pack(side="right")
        self.input_label = ctk.CTkLabel(
            main, text="Paste a video or playlist link, or import a TXT file.", height=22
        )
        self.input_label.pack(anchor="w")
        times = ctk.CTkFrame(main, fg_color="transparent")
        times.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(times, text="Start").pack(side="left")
        self.start_entry = ctk.CTkEntry(times, textvariable=self.range_start, width=85)
        self.start_entry.pack(side="left", padx=(6, 12))
        ctk.CTkLabel(times, text="End").pack(side="left")
        self.end_entry = ctk.CTkEntry(times, textvariable=self.range_end, width=85)
        self.end_entry.pack(side="left", padx=(6, 12))
        ctk.CTkLabel(times, text="Optional: SS / MM:SS / HH:MM:SS").pack(side="left")
        self.start_entry.configure(state="disabled")
        self.end_entry.configure(state="disabled")
        row = ctk.CTkFrame(main, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Destination").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(row, textvariable=self.destination).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(row, text="Browse...", width=85, command=self._browse).pack(side="right")
        ctk.CTkCheckBox(
            main, text="Create a subfolder for the source", variable=self.subfolder, height=24
        ).pack(anchor="w", pady=6)
        tracks = ctk.CTkFrame(main, fg_color="transparent")
        tracks.pack(fill="x", pady=(0, 6))
        tracks.grid_columnconfigure((0, 1), weight=1, uniform="tracks")
        for audio, column, title in (
            (True, 0, "Audio languages"),
            (False, 1, "Subtitle languages"),
        ):
            panel = ctk.CTkFrame(tracks)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 5) if audio else (5, 0))
            ctk.CTkLabel(panel, text=title, font=ctk.CTkFont(weight="bold"), height=24).pack(
                anchor="w", padx=8
            )
            picker = LanguagePicker(
                panel,
                options=language_options(audio),
                command=partial(self._add_track, audio),
            )
            picker.pack(fill="x", padx=8, pady=(0, 5))
            picker.set("Add language...")
            listing = tk.Listbox(
                panel,
                height=4,
                font=("Segoe UI", 11),
                exportselection=False,
                activestyle="none",
                borderwidth=0,
                highlightthickness=0,
                background=self._apply_appearance_mode(
                    ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
                ),
                foreground=self._apply_appearance_mode(
                    ctk.ThemeManager.theme["CTkLabel"]["text_color"]
                ),
                selectbackground="#1f6aa5",
                selectforeground="white",
            )
            listing.pack(fill="x", padx=8)
            actions = ctk.CTkFrame(panel, fg_color="transparent")
            actions.pack(fill="x", padx=8, pady=5)
            for label, callback, width in (
                ("Up", lambda is_audio=audio: self._move_selected_track(is_audio, -1), 40),
                ("Down", lambda is_audio=audio: self._move_selected_track(is_audio, 1), 50),
                ("Remove", lambda is_audio=audio: self._remove_selected_track(is_audio), 65),
            ):
                ctk.CTkButton(actions, text=label, command=callback, width=width, height=25).pack(
                    side="left", padx=(0, 5)
                )
            if audio:
                self.language_menu = picker
                self.audio_list = listing
                ctk.CTkButton(
                    actions,
                    text="Set default",
                    width=85,
                    height=25,
                    command=self._make_default_audio,
                ).pack(side="right")
                ctk.CTkLabel(panel, text="* Playback default", height=24).pack(
                    anchor="w", padx=8, pady=(0, 2)
                )
            else:
                self.subtitle_menu = picker
                self.subtitle_list = listing
                ctk.CTkCheckBox(
                    panel,
                    text="Allow automatic subtitles",
                    variable=self.automatic_subtitles,
                    height=24,
                ).pack(anchor="w", padx=8, pady=(0, 2))
        self._render_tracks()
        options = ctk.CTkFrame(main, fg_color="transparent")
        options.pack(fill="x", pady=(0, 8))
        options.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="options")
        for column, title in enumerate(
            ("Maximum quality", "Format", "If no requested audio", "Impersonation")
        ):
            ctk.CTkLabel(options, text=title, height=22, anchor="w").grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 8) if column < 3 else 0,
            )
        self.quality_menu = ctk.CTkOptionMenu(
            options,
            values=["Best available", "1080p", "720p", "480p"],
            command=self._quality_changed,
        )
        self.quality_menu.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.quality_menu.set(
            {"best": "Best available", "1080": "1080p", "720": "720p", "480": "480p"}[
                self.quality.get()
            ]
        )
        ctk.CTkOptionMenu(options, values=["mkv", "mp4"], variable=self.output_container).grid(
            row=1, column=1, sticky="ew", padx=(0, 8)
        )
        self.missing_menu = ctk.CTkOptionMenu(
            options,
            values=["Skip video", "Use original/default"],
            command=lambda label: self.missing.set("skip" if label == "Skip video" else "fallback"),
        )
        self.missing_menu.grid(row=1, column=2, sticky="ew", padx=(0, 8))
        self.missing_menu.set(
            "Skip video" if self.missing.get() == "skip" else "Use original/default"
        )
        self.impersonation_menu = ctk.CTkOptionMenu(
            options,
            values=["Automatic"],
            command=lambda label: self.impersonation.set(
                "auto" if label == "Automatic" else label.lower()
            ),
        )
        self.impersonation_menu.grid(row=1, column=3, sticky="ew")
        self.impersonation_menu.set(
            "Automatic" if self.impersonation.get() == "auto" else self.impersonation.get().title()
        )
        actions = ctk.CTkFrame(main, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 8))
        self.start_button = ctk.CTkButton(actions, text="Download", command=self._start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ctk.CTkButton(
            actions, text="Cancel", state="disabled", fg_color="gray", command=self._cancel
        )
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.install_button = ctk.CTkButton(
            actions, text="Update tools", fg_color="#555", command=self._install
        )
        self.bar = ctk.CTkProgressBar(main)
        self.bar.pack(fill="x")
        self.bar.set(0)
        self.status_label = ctk.CTkLabel(
            main, text="Ready", wraplength=740, justify="left", height=24
        )
        self.status_label.pack(anchor="w", pady=(3, 3))
        self.log = ctk.CTkTextbox(main, height=75)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    def _show_about(self) -> None:
        if self.closing:
            return
        if self._about_window is not None and self._about_window.winfo_exists():
            self._about_window.lift()
            self._about_window.focus_set()
            return
        self._about_window = AboutWindow(self)

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
                    self.events.put(("impersonation_targets", manager.impersonation_targets()))
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
        self.range_start.set("")
        self.range_end.set("")
        state = "disabled"
        try:
            source = classify_url(self.url.get())
            if source.kind in {"video", "ambiguous"}:
                state = "normal"
            label = {
                "video": "Video detected",
                "playlist": "Playlist detected",
                "ambiguous": "Video and playlist detected; you will choose before downloading",
            }[source.kind]
        except ValueError:
            label = "Paste a video or playlist link, or import a TXT file."
        self.input_label.configure(text=label)
        self.start_entry.configure(state=state)
        self.end_entry.configure(state=state)

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
        self.imported_links = imported.requests
        self.imported_name = Path(filename).stem
        self.input_label.configure(text=f"Imported {len(imported.links)} videos in file order")

    def _add_track(self, audio: bool, label: str) -> None:
        language = language_options(audio).get(label)
        if language is None:
            return
        values = self.audio_languages if audio else self.subtitle_languages
        if language.lower() not in [code.lower() for code in values]:
            values.append(language)
        self._render_tracks()
        listing = self.audio_list if audio else self.subtitle_list
        index = next(i for i, code in enumerate(values) if code.lower() == language.lower())
        listing.selection_clear(0, "end")
        listing.selection_set(index)
        listing.see(index)
        (self.language_menu if audio else self.subtitle_menu).set("Add language...")

    def _selected_track(self, audio: bool) -> str | None:
        listing = self.audio_list if audio else self.subtitle_list
        selection = listing.curselection()
        values = self.audio_languages if audio else self.subtitle_languages
        return values[selection[0]] if selection else None

    def _remove_selected_track(self, audio: bool) -> None:
        language = self._selected_track(audio)
        if language is not None:
            self._remove_track(language, audio)

    def _move_selected_track(self, audio: bool, direction: int) -> None:
        language = self._selected_track(audio)
        if language is not None:
            self._move_track(language, audio, direction)
            listing = self.audio_list if audio else self.subtitle_list
            values = self.audio_languages if audio else self.subtitle_languages
            listing.selection_clear(0, "end")
            listing.selection_set(values.index(language))
            listing.see(values.index(language))

    def _make_default_audio(self) -> None:
        language = self._selected_track(True)
        if language is not None:
            self.default_audio.set(language)
            self._render_tracks()

    def _remove_track(self, language: str, audio: bool) -> None:
        values = self.audio_languages if audio else self.subtitle_languages
        if audio and len(values) == 1:
            messagebox.showwarning("Audio", "At least one audio language is required.")
            return
        values.remove(language)
        if audio and self.default_audio.get() == language:
            self.default_audio.set(values[0])
        self._render_tracks()

    def _move_track(self, language: str, audio: bool, direction: int) -> None:
        values = self.audio_languages if audio else self.subtitle_languages
        index = values.index(language)
        target = index + direction
        if 0 <= target < len(values):
            values[index], values[target] = values[target], values[index]
            self._render_tracks()

    def _render_tracks(self) -> None:
        for audio, listing, values in (
            (True, self.audio_list, self.audio_languages),
            (False, self.subtitle_list, self.subtitle_languages),
        ):
            selection = listing.curselection()
            selected_index = selection[0] if selection else 0
            listing.delete(0, "end")
            for language in values:
                label = LANGUAGE_NAMES.get(language, LANGUAGES.get(language, language))
                prefix = "* " if audio and language == self.default_audio.get() else "  "
                listing.insert("end", prefix + label)
            if values:
                listing.selection_set(min(selected_index, len(values) - 1))

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
                    "audio_languages": self.audio_languages,
                    "subtitle_languages": self.subtitle_languages,
                    "default_audio": self.default_audio.get(),
                    "automatic_subtitles": self.automatic_subtitles.get(),
                    "container": self.output_container.get(),
                    "impersonation": self.impersonation.get(),
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
        url: str | DownloadRequest | list[DownloadRequest]
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
            if is_playlist and (self.range_start.get().strip() or self.range_end.get().strip()):
                messagebox.showerror("Time range", "Clear Start and End to download a playlist.")
                return
            if not is_playlist:
                try:
                    time_range = parse_time_range(self.range_start.get(), self.range_end.get())
                except ValueError as exc:
                    messagebox.showerror("Time range", str(exc))
                    return
                if time_range:
                    url = DownloadRequest(url, time_range)
        folder = Path(self.destination.get().strip()).expanduser()
        if not str(self.destination.get()).strip():
            messagebox.showerror("Folder", "Choose a destination folder.")
            return
        prefs = Preferences(
            missing=self.missing.get(),
            quality=self.quality.get(),
            playlist_subfolder=self.subfolder.get(),
            audio_languages=tuple(self.audio_languages),
            subtitle_languages=tuple(self.subtitle_languages),
            default_audio=self.default_audio.get(),
            automatic_subtitles=self.automatic_subtitles.get(),
            container=self.output_container.get(),
            impersonation=self.impersonation.get(),
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
                elif kind == "impersonation_targets":
                    self.impersonation_menu.configure(
                        values=["Automatic", *[name.title() for name in event[1]]]
                    )
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
            assert app.start_entry.cget("state") == "normal"
            app.range_start.set("01:30")
            app.range_end.set("03:00")
            app.url.set("https://www.youtube.com/playlist?list=PL_test")
            assert app.start_entry.cget("state") == app.end_entry.cget("state") == "disabled"
            assert app.range_start.get() == app.range_end.get() == ""
            app.url.set("TXT: clips.txt")
            assert app.start_entry.cget("state") == "disabled"
            assert app._app_icon.width() == 256
            assert (Path(__file__).with_name("assets") / "app-icon.ico").is_file()
            app._show_about()
            about = app._about_window
            assert about is not None and about.winfo_exists()
            about.withdraw()
            assert about.version_label.cget("text") == f"Version {__version__}"
            assert "Copyright (c) 2026 ipeidro" in about.notices.get("1.0", "end")
            about.destroy()
            args.smoke_test.write_text(
                json.dumps({"status": "ok", "title": app.title()}), encoding="utf-8"
            )
            app.destroy()

        app.after(300, finish_smoke)
    app.mainloop()


if __name__ == "__main__":
    main()
