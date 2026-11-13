import json

import pytest

from youtube_smart_downloader import settings


@pytest.fixture
def config(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "config_file", lambda: path)
    return path


@pytest.mark.parametrize(
    "text",
    [
        "invalid",
        "[]",
        '{"language": [], "quality": null, "missing": "bad", "mode": 7, "playlist_subfolder": "false", "destination": {}}',
    ],
)
def test_invalid_settings_are_normalized(config, text):
    config.write_text(text, encoding="utf-8")
    data = settings.load()
    assert data["language"] == "es-ES" and data["quality"] == "best"
    assert "mode" not in data and data["missing"] == "skip"
    assert data["playlist_subfolder"] is True
    assert isinstance(data["destination"], str)


def test_atomic_preferences_round_trip(config):
    settings.save({"language": "es-ES", "playlist_subfolder": False, "destination": "C:/Videos"})
    assert settings.load()["language"] == "es-ES"
    assert settings.load()["playlist_subfolder"] is False
    assert json.loads(config.read_text(encoding="utf-8"))["destination"] == "C:/Videos"
    assert not list(config.parent.glob("*.tmp"))


def test_failed_atomic_replace_preserves_previous_settings(config, monkeypatch):
    settings.save({"language": "en"})

    def fail(*args):
        raise PermissionError("fixture")

    monkeypatch.setattr(type(config), "replace", fail)
    with pytest.raises(PermissionError):
        settings.save({"language": "es"})
    assert settings.load()["language"] == "en"
    assert not list(config.parent.glob("*.tmp"))


def test_multi_track_preferences_round_trip(config):
    prefs = {
        "audio_languages": ["original", "es-ES", "fr"],
        "subtitle_languages": ["es", "en"],
        "default_audio": "fr",
        "automatic_subtitles": True,
        "container": "mkv",
    }
    settings.save(prefs)
    loaded = settings.load()
    assert all(loaded[key] == value for key, value in prefs.items())


def test_initial_languages_and_playback_default(config):
    data = settings.load()
    assert data["container"] == "mkv"
    assert data["audio_languages"] == ["es-ES", "en"]
    assert data["default_audio"] == "es-ES"
    assert data["subtitle_languages"] == ["es", "en"]


def test_saved_language_selections_are_preserved(config):
    settings.save({"audio_languages": ["fr"], "default_audio": "fr", "subtitle_languages": []})
    data = settings.load()
    assert data["audio_languages"] == ["fr"]
    assert data["default_audio"] == "fr"
    assert data["subtitle_languages"] == []


def test_legacy_spanish_setup_adopts_new_initial_languages(config):
    config.write_text(json.dumps({"language": "es-ES"}), encoding="utf-8")
    data = settings.load()
    assert data["container"] == "mkv"
    assert data["audio_languages"] == ["es-ES", "en"]
    assert data["default_audio"] == "es-ES"
    assert data["subtitle_languages"] == ["es", "en"]
