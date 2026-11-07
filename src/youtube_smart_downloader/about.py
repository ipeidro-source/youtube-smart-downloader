"""Application identity, project links and locally readable release licenses."""

from pathlib import Path
import os
import sys
import webbrowser

import customtkinter as ctk

from . import APP_NAME, AUTHOR, COPYRIGHT, LICENSE_NAME, PROJECT_URL, SUPPORT_URL, __version__


def license_text() -> str:
    if getattr(sys, "frozen", False):
        folder = Path(getattr(sys, "_MEIPASS")) / "release-docs"
        files = (folder / "LICENSE.txt", folder / "THIRD_PARTY_NOTICES.txt")
    else:
        root = Path(__file__).resolve().parents[2]
        files = (root / "LICENSE", root / "docs/THIRD_PARTY.md")
    try:
        return "\n\n".join(path.read_text(encoding="utf-8") for path in files)
    except OSError as exc:
        return f"License notices could not be read: {exc}\n\nSee {PROJECT_URL}/blob/main/LICENSE"


class AboutWindow(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        self.title(f"About {APP_NAME}")
        if os.name == "nt":
            self.iconbitmap(str(Path(__file__).with_name("assets") / "app-icon.ico"))
        self.geometry("540x480")
        self.minsize(500, 440)
        self.transient(master)
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=16, pady=(4, 10))
        overview = tabs.add("About")
        licenses = tabs.add("Licenses")
        ctk.CTkLabel(overview, text=APP_NAME, font=ctk.CTkFont(size=22, weight="bold")).pack(
            pady=(12, 8)
        )
        self.version_label = ctk.CTkLabel(overview, text=f"Version {__version__}")
        self.version_label.pack()
        ctk.CTkLabel(
            overview, text=f"Developed by {AUTHOR}\n{COPYRIGHT}\n{LICENSE_NAME} License"
        ).pack(pady=(4, 10))
        ctk.CTkLabel(
            overview,
            text="Built with Python and CustomTkinter.\nDownloads use yt-dlp; media processing uses FFmpeg.\nOnly download content you have permission to use.",
            wraplength=460,
        ).pack(pady=(0, 14))
        links = ctk.CTkFrame(overview, fg_color="transparent")
        links.pack(fill="x", padx=8)
        links.grid_columnconfigure((0, 1), weight=1)
        for index, (label, url) in enumerate(
            (
                ("Project", PROJECT_URL),
                ("Support", SUPPORT_URL),
                ("Privacy", PROJECT_URL + "/blob/main/docs/PRIVACY.md"),
                ("Code signing policy", PROJECT_URL + "/blob/main/docs/CODE_SIGNING.md"),
            )
        ):
            ctk.CTkButton(
                links, text=label, command=lambda url=url: webbrowser.open_new_tab(url)
            ).grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)
        self.notices = ctk.CTkTextbox(licenses, wrap="word")
        self.notices.pack(fill="both", expand=True, padx=4, pady=4)
        self.notices.insert("1.0", license_text())
        self.notices.configure(state="disabled")
        ctk.CTkButton(self, text="Close", command=self.destroy).pack(pady=(0, 12))
