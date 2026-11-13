"""Bounded, searchable language dropdown with ordinary mouse-wheel scrolling."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk


class LanguagePicker(ctk.CTkButton):
    def __init__(
        self, master: Any, options: dict[str, str], command: Callable[[str], None]
    ) -> None:
        super().__init__(master, text="Add language...", anchor="w", command=self._open)
        self.options = options
        self.on_select = command
        self.popup: tk.Toplevel | None = None

    def set(self, text: str) -> None:
        self.configure(text=text)

    def _close(self) -> None:
        popup = self.popup
        self.popup = None
        if popup is not None:
            if popup.grab_current() == popup:
                popup.grab_release()
            self.winfo_toplevel().focus_set()
            popup.destroy()

    def _open(self) -> None:
        if self.popup is not None:
            self._close()
            return
        # A borderless Tk window avoids CTkToplevel's delayed Windows titlebar
        # callbacks restoring focus to a widget from the previous popup.
        popup = tk.Toplevel(
            self,
            background=self._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]),
        )
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.winfo_toplevel())
        self.popup = popup
        scale = self._get_widget_scaling()
        width = max(self.winfo_width(), round(320 * scale))
        height = round(280 * scale)
        x = min(self.winfo_rootx(), max(0, self.winfo_screenwidth() - width))
        y = self.winfo_rooty() + self.winfo_height()
        if y + height > self.winfo_screenheight():
            y = max(0, self.winfo_rooty() - height)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        frame = ctk.CTkFrame(popup, border_width=1)
        frame.pack(fill="both", expand=True)
        self.search = tk.StringVar(master=popup)
        entry = ctk.CTkEntry(
            frame, textvariable=self.search, placeholder_text="Search language or code..."
        )
        entry.pack(fill="x", padx=7, pady=7)
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        self.listing = tk.Listbox(
            body,
            exportselection=False,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 11),
            background=self._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]),
            foreground=self._apply_appearance_mode(
                ctk.ThemeManager.theme["CTkLabel"]["text_color"]
            ),
            selectbackground="#1f6aa5",
            selectforeground="white",
        )
        scrollbar = ctk.CTkScrollbar(body, command=self.listing.yview)
        scrollbar.pack(side="right", fill="y")
        self.listing.configure(yscrollcommand=scrollbar.set)
        self.listing.pack(side="left", fill="both", expand=True)
        self.search.trace_add("write", self._filter)
        self._filter()
        self.listing.bind("<MouseWheel>", self._wheel)
        self.listing.bind("<Button-4>", lambda event: self._scroll(-3))
        self.listing.bind("<Button-5>", lambda event: self._scroll(3))
        self.listing.bind("<ButtonRelease-1>", self._choose)
        self.listing.bind("<Return>", self._choose)
        entry.bind("<Return>", self._choose)
        entry.bind("<Down>", lambda event: self.listing.focus_set())
        popup.bind("<Escape>", lambda event: self._close())
        popup.bind("<Button-1>", self._outside_click, add="+")
        popup.deiconify()

        def activate() -> None:
            if self.popup is popup and popup.winfo_exists():
                popup.grab_set()
                entry.focus_force()

        # Keyboard focus must be assigned after the native window has mapped.
        popup.after_idle(activate)

    def _filter(self, *_args: Any) -> None:
        terms = self.search.get().casefold().split()
        self.listing.delete(0, "end")
        for label in self.options:
            if all(term in label.casefold() for term in terms):
                self.listing.insert("end", label)
        if self.listing.size():
            self.listing.selection_set(0)

    def _scroll(self, units: int) -> str:
        self.listing.yview_scroll(units, "units")
        return "break"

    def _wheel(self, event: Any) -> str:
        # Windows typically sends multiples of 120; touchpads/macOS may send smaller deltas.
        if not event.delta:
            return "break"
        steps = max(1, abs(event.delta) // 120)
        return self._scroll(-steps * 3 if event.delta > 0 else steps * 3)

    def _choose(self, _event: Any = None) -> str:
        selected = self.listing.curselection()
        if selected:
            label = self.listing.get(selected[0])
            self._close()
            self.on_select(label)
        return "break"

    def _outside_click(self, event: Any) -> None:
        popup = self.popup
        if popup is not None and not (
            popup.winfo_rootx() <= event.x_root < popup.winfo_rootx() + popup.winfo_width()
            and popup.winfo_rooty() <= event.y_root < popup.winfo_rooty() + popup.winfo_height()
        ):
            self._close()
