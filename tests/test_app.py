"""UI lifecycle checks without creating a display or running an event loop."""

from types import SimpleNamespace
import threading
import queue
from unittest.mock import Mock

import pytest

from youtube_smart_downloader.app import App
from youtube_smart_downloader.tools import SPECS, ToolStatus


def test_close_waits_for_worker_and_requests_cancellation(monkeypatch):
    monkeypatch.setattr("youtube_smart_downloader.app.messagebox.askyesno", lambda *args: True)
    app = SimpleNamespace(
        closing=False,
        worker=Mock(),
        engine=Mock(),
        _save=Mock(),
        start_button=Mock(),
        install_button=Mock(),
        cancel_button=Mock(),
        status_label=Mock(),
        destroy=Mock(),
        after=Mock(),
        check_event=threading.Event(),
        check_worker=None,
        import_button=Mock(),
    )
    app.worker.is_alive.return_value = True
    app._finish_close = lambda: App._finish_close(app)
    App._close(app)
    app.engine.cancel.assert_called_once()
    app.destroy.assert_not_called()
    assert app.closing
    assert app.after.call_args.args[0] == 100
    app.worker.is_alive.return_value = False
    App._finish_close(app)
    app.destroy.assert_called_once()


def test_preference_write_error_is_shown_without_aborting_callback(monkeypatch):
    monkeypatch.setattr("youtube_smart_downloader.app.save", Mock(side_effect=OSError("read only")))
    warning = Mock()
    monkeypatch.setattr("youtube_smart_downloader.app.messagebox.showwarning", warning)
    app = SimpleNamespace(
        **{
            key: Mock()
            for key in (
                "destination",
                "mode",
                "language",
                "missing",
                "quality",
                "subfolder",
                "_log",
            )
        }
    )
    App._save(app)
    warning.assert_called_once()
    app._log.assert_called_once()


def tools_ui():
    app = SimpleNamespace(
        closing=False,
        worker=None,
        start_button=Mock(),
        cancel_button=Mock(),
        install_button=Mock(),
        import_button=Mock(),
        status_label=Mock(),
        _log=Mock(),
        _close=Mock(),
        _install=Mock(),
    )
    app._set_busy = lambda busy: App._set_busy(app, busy)
    return app


@pytest.mark.parametrize("install", [True, False])
def test_missing_tools_block_download_and_offer_install_or_exit(monkeypatch, install):
    ask = Mock(return_value=install)
    monkeypatch.setattr("youtube_smart_downloader.app.messagebox.askyesno", ask)
    app = tools_ui()
    App._tools_local(app, [ToolStatus(SPECS[2], error="Not found")])
    assert not app.tools_ready
    app.start_button.configure.assert_called_with(state="disabled")
    assert "ffprobe" in ask.call_args.args[1]
    if install:
        app._install.assert_called_once_with(install=True)
        app._close.assert_not_called()
    else:
        app._close.assert_called_once()
        app._install.assert_not_called()


def test_working_tools_allow_startup_without_a_popup(monkeypatch):
    ask = Mock()
    monkeypatch.setattr("youtube_smart_downloader.app.messagebox.askyesno", ask)
    app = tools_ui()
    App._tools_local(
        app, [ToolStatus(spec, path="/tools/" + spec.name, version="1.0") for spec in SPECS]
    )
    assert app.tools_ready
    app.start_button.configure.assert_called_with(state="normal")
    ask.assert_not_called()


@pytest.mark.parametrize(
    "update,visible", [("unknown", False), ("current", False), ("available", True)]
)
def test_update_button_only_appears_for_confirmed_updates(update, visible):
    app = tools_ui()
    app.tools_ready = True
    App._tools_updates(app, [ToolStatus(SPECS[0], path="/tool", version="1.0", update=update)])
    assert app.install_button.pack.called is visible
    assert app.install_button.pack_forget.called is not visible
    app.start_button.configure.assert_called_with(state="normal")


@pytest.mark.parametrize("choice,playlist", [(True, True), (False, False), (None, None)])
def test_ambiguous_link_requires_scope_choice(monkeypatch, tmp_path, choice, playlist):
    monkeypatch.setattr(
        "youtube_smart_downloader.app.messagebox.askyesnocancel", lambda *args: choice
    )
    engine = Mock()
    monkeypatch.setattr("youtube_smart_downloader.app.DownloadEngine", lambda *args: engine)
    monkeypatch.setattr(
        "youtube_smart_downloader.app.threading.Thread",
        lambda target: SimpleNamespace(start=target),
    )

    def value(text):
        return SimpleNamespace(get=lambda: text)

    app = SimpleNamespace(
        tools_ready=True,
        worker=None,
        imported_links=[],
        url=value("https://www.youtube.com/watch?v=abcdefghijk&list=PL_test"),
        destination=value(str(tmp_path)),
        language=value("es"),
        missing=value("skip"),
        quality=value("best"),
        subfolder=value(True),
        _save=Mock(),
        _set_busy=Mock(),
        bar=Mock(),
        events=queue.Queue(),
    )
    App._start(app)
    if choice is None:
        engine.download.assert_not_called()
    else:
        assert engine.download.call_args.args[2] is playlist
        assert engine.download.call_args.args[0] == (
            "https://www.youtube.com/playlist?list=PL_test"
            if playlist
            else "https://www.youtube.com/watch?v=abcdefghijk"
        )


def test_txt_import_requires_review_before_discarding_invalid_lines(monkeypatch, tmp_path):
    text_file = tmp_path / "links.txt"
    text_file.write_text(
        "https://youtu.be/abcdefghijk\ninvalid\nhttps://youtu.be/abcdefghijk", encoding="utf-8"
    )
    monkeypatch.setattr(
        "youtube_smart_downloader.app.filedialog.askopenfilename", lambda **kwargs: str(text_file)
    )
    ask = Mock(return_value=False)
    monkeypatch.setattr("youtube_smart_downloader.app.messagebox.askyesno", ask)
    app = SimpleNamespace(_log=Mock(), url=Mock(), imported_links=[], input_label=Mock())
    App._import_links(app)
    assert not app.imported_links and not app.url.set.called
    assert "1 invalid lines and 1 duplicates" in ask.call_args.args[1]
    ask.return_value = True
    App._import_links(app)
    assert app.imported_links == ["https://www.youtube.com/watch?v=abcdefghijk"]
    assert app.imported_name == "links"


def test_txt_name_is_forwarded_to_the_download_job(monkeypatch, tmp_path):
    engine = Mock()
    monkeypatch.setattr("youtube_smart_downloader.app.DownloadEngine", lambda *args: engine)
    monkeypatch.setattr(
        "youtube_smart_downloader.app.threading.Thread",
        lambda target: SimpleNamespace(start=target),
    )

    def value(text):
        return SimpleNamespace(get=lambda: text)

    app = SimpleNamespace(
        tools_ready=True,
        worker=None,
        imported_links=["https://www.youtube.com/watch?v=abcdefghijk"],
        imported_name="My links",
        destination=value(str(tmp_path)),
        language=value("es"),
        missing=value("skip"),
        quality=value("best"),
        subfolder=value(True),
        _save=Mock(),
        _set_busy=Mock(),
        bar=Mock(),
        events=queue.Queue(),
    )
    App._start(app)
    assert engine.download.call_args.kwargs["batch_name"] == "My links"
    assert engine.download.call_args.args[3].playlist_subfolder


def test_editing_the_input_clears_the_previous_txt_name():
    app = SimpleNamespace(
        imported_links=["old link"],
        imported_name="Old list",
        url=SimpleNamespace(get=lambda: "https://youtu.be/abcdefghijk"),
        input_label=Mock(),
    )
    App._input_changed(app)
    assert app.imported_name is None and app.imported_links == []
