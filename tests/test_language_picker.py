"""Windows regression: type through keyboard focus, rather than setting StringVar."""

import sys
import time
from types import SimpleNamespace

import customtkinter as ctk
import pytest

from youtube_smart_downloader.app import language_options
from youtube_smart_downloader.language_picker import LanguagePicker


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows desktop Tk")


def settle(root):
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)


def test_repeated_keyboard_search_across_both_pickers():
    root = ctk.CTk()
    root.attributes("-alpha", 0.0)
    selected = []
    pickers = [
        LanguagePicker(root, language_options(audio), selected.append) for audio in (True, False)
    ]
    for picker in pickers:
        picker.pack()
    try:
        settle(root)
        for index, query in enumerate(("french", "japanese", "german", "italian") * 3):
            picker = pickers[index % 2]
            picker._open()
            settle(root)
            focus = root.focus_get()
            assert focus is not None and focus.winfo_class() == "Entry"
            assert str(focus).startswith(str(picker.popup))
            for character in query:
                focus.event_generate("<KeyPress>", keysym=character)
            root.update()
            assert picker.search.get() == query
            assert picker.listing.size() == 1
            assert query in picker.listing.get(0).lower()
            if index % 2:
                focus.event_generate("<Return>")
            else:
                picker.listing.event_generate("<ButtonRelease-1>", x=5, y=5)
            root.update()
            assert picker.popup is None
            assert root.grab_current() is None
        assert len(selected) == 12
        for picker in pickers:
            for cancel in ("escape", "outside"):
                picker._open()
                settle(root)
                if cancel == "escape":
                    root.focus_get().event_generate("<Escape>")
                else:
                    picker._outside_click(SimpleNamespace(x_root=-1, y_root=-1))
                root.update()
                assert picker.popup is None and root.grab_current() is None
    finally:
        root.destroy()
