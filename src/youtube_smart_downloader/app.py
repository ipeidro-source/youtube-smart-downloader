"""Spanish-language, Windows-first desktop GUI."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .core import LANGUAGES, Preferences, valid_youtube_url
from .engine import Cancelled, DownloadEngine, install_missing
from .settings import load, save


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube Smart Downloader")
        self.geometry("760x720")
        self.minsize(650, 650)
        ctk.set_appearance_mode("System")
        data = load()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.engine: DownloadEngine | None = None
        self.url = tk.StringVar(value="")
        self.destination = tk.StringVar(value=str(data.get("destination") or Path.home() / "Downloads"))
        self.mode = tk.StringVar(value=str(data.get("mode") or "playlist"))
        self.language = tk.StringVar(value=str(data.get("language") or "es"))
        self.missing = tk.StringVar(value=str(data.get("missing") or "skip"))
        self.quality = tk.StringVar(value=str(data.get("quality") or "best"))
        self.subfolder = tk.BooleanVar(value=bool(data.get("playlist_subfolder", True)))
        self._build()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        container = ctk.CTkScrollableFrame(self, corner_radius=0)
        container.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(container, text="YouTube Smart Downloader", font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(container, text="Descarga vídeos y listas con control del idioma de audio.").pack(anchor="w", pady=(0, 18))
        ctk.CTkLabel(container, text="¿Qué quieres descargar?").pack(anchor="w")
        ctk.CTkSegmentedButton(container, values=["Vídeo", "Lista"], command=self._mode_changed).pack(fill="x", pady=(6, 14))
        # A separate widget reference ensures the saved value is reflected on startup.
        segment = container.winfo_children()[-1]
        segment.set("Lista" if self.mode.get() == "playlist" else "Vídeo")
        ctk.CTkLabel(container, text="Enlace de YouTube").pack(anchor="w")
        ctk.CTkEntry(container, textvariable=self.url, placeholder_text="https://www.youtube.com/...").pack(fill="x", pady=(5, 14))
        ctk.CTkLabel(container, text="Carpeta de destino").pack(anchor="w")
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=(5, 14))
        ctk.CTkEntry(row, textvariable=self.destination).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Examinar…", width=100, command=self._browse).pack(side="right")
        ctk.CTkCheckBox(container, text="Crear subcarpeta con el nombre de la lista", variable=self.subfolder).pack(anchor="w", pady=(0, 14))
        grid = ctk.CTkFrame(container, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(grid, text="Idioma del audio").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(grid, text="Calidad máxima").grid(row=0, column=1, sticky="w")
        languages = list(LANGUAGES.values())
        initial_language = LANGUAGES.get(self.language.get(), LANGUAGES["es"])
        self.language_menu = ctk.CTkOptionMenu(grid, values=languages, command=self._language_changed)
        self.language_menu.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(5, 14))
        self.language_menu.set(initial_language)
        self.quality_menu = ctk.CTkOptionMenu(grid, values=["Mejor disponible", "1080p", "720p", "480p"], command=self._quality_changed)
        self.quality_menu.grid(row=1, column=1, sticky="ew", pady=(5, 14))
        self.quality_menu.set({"best": "Mejor disponible", "1080": "1080p", "720": "720p", "480": "480p"}.get(self.quality.get(), "Mejor disponible"))
        ctk.CTkLabel(container, text="Si no existe ese idioma:").pack(anchor="w")
        ctk.CTkRadioButton(container, text="Omitir el vídeo y avisar (recomendado)", variable=self.missing, value="skip").pack(anchor="w", pady=(5, 5))
        ctk.CTkRadioButton(container, text="Usar audio original/predeterminado como alternativa", variable=self.missing, value="fallback").pack(anchor="w", pady=(0, 15))
        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 15))
        self.start_button = ctk.CTkButton(actions, text="Descargar", command=self._start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ctk.CTkButton(actions, text="Cancelar", state="disabled", fg_color="gray", command=self._cancel)
        self.cancel_button.pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Instalar herramientas", fg_color="#555", command=self._install).pack(side="left")
        self.bar = ctk.CTkProgressBar(container)
        self.bar.pack(fill="x")
        self.bar.set(0)
        self.status_label = ctk.CTkLabel(container, text="Preparado", wraplength=650, justify="left")
        self.status_label.pack(anchor="w", pady=(9, 6))
        self.log = ctk.CTkTextbox(container, height=115)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")
        missing = DownloadEngine.missing_tools()
        if missing:
            self._log("Herramientas no detectadas: " + ", ".join(missing) + ". Pulsa «Instalar herramientas».")

    def _mode_changed(self, value: str) -> None:
        self.mode.set("playlist" if value == "Lista" else "video")

    def _language_changed(self, value: str) -> None:
        self.language.set(next(key for key, label in LANGUAGES.items() if label == value))

    def _quality_changed(self, value: str) -> None:
        self.quality.set({"Mejor disponible": "best", "1080p": "1080", "720p": "720", "480p": "480"}[value])

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
        save({"destination": self.destination.get(), "mode": self.mode.get(),
              "language": self.language.get(), "missing": self.missing.get(),
              "quality": self.quality.get(), "playlist_subfolder": self.subfolder.get()})

    def _set_busy(self, busy: bool) -> None:
        self.start_button.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        url = self.url.get().strip()
        if not valid_youtube_url(url):
            messagebox.showerror("Enlace inválido", "Introduce un enlace http(s) de YouTube válido.")
            return
        folder = Path(self.destination.get().strip()).expanduser()
        if not str(self.destination.get()).strip():
            messagebox.showerror("Carpeta", "Elige una carpeta de destino.")
            return
        prefs = Preferences(self.language.get(), self.missing.get(), self.quality.get(), self.subfolder.get())
        self._save()
        is_playlist = self.mode.get() == "playlist"
        self.bar.set(0)
        self._set_busy(True)
        self.engine = DownloadEngine(lambda s: self.events.put(("status", s)),
                                     lambda n, t, p: self.events.put(("progress", n, t, p)))

        def work() -> None:
            try:
                result = self.engine.download(url, folder, is_playlist, prefs)
                self.events.put(("done", result))
            except Cancelled:
                self.events.put(("stopped",))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.engine:
            self.engine.cancel()
            self._log("Cancelación solicitada.")

    def _install(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not messagebox.askyesno("Instalar herramientas", "¿Instalar yt-dlp, FFmpeg y Deno mediante winget? Se requiere conexión a Internet."):
            return
        self._set_busy(True)

        def work() -> None:
            try:
                install_missing(lambda s: self.events.put(("status", s)))
                self.events.put(("installed",))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
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
                    summary = f"Completado: {len(report['downloaded'])} procesados; {len(report['omitted'])} omitidos; {len(report['failed'])} errores.\nInforme: {report['directory']}"
                    self._log(summary)
                    messagebox.showinfo("Informe de descarga", summary)
                elif kind == "stopped":
                    self._set_busy(False)
                    self._log("Descarga cancelada. Los archivos parciales se podrán reanudar.")
                elif kind == "installed":
                    self._set_busy(False)
                    messagebox.showinfo("Instalación", "Instalación finalizada. Cierra y vuelve a abrir esta aplicación.")
                elif kind == "error":
                    self._set_busy(False)
                    self._log(event[1])
                    messagebox.showerror("Error", event[1][:700])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Cerrar", "Hay una operación en curso. ¿Cancelar y cerrar?"):
                return
            if self.engine:
                self.engine.cancel()
        self._save()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
