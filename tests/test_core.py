from pathlib import Path

import pytest

from youtube_smart_downloader.core import (
    Preferences,
    download_args,
    language_matches,
    output_template,
    safe_name,
    select_audio,
    select_video,
    valid_youtube_url,
)


FORMATS = [
    {"format_id": "v1080", "height": 1080, "vcodec": "avc1", "acodec": "none", "tbr": 1500},
    {"format_id": "v720", "height": 720, "vcodec": "vp9", "acodec": "none", "tbr": 800},
    {"format_id": "a_es", "vcodec": "none", "acodec": "opus", "language": "es", "abr": 128},
    {"format_id": "a_es_ES", "vcodec": "none", "acodec": "opus", "language": "es-ES", "abr": 110},
    {"format_id": "a_latam", "vcodec": "none", "acodec": "opus", "language": "es-419", "abr": 130},
    {"format_id": "a_en", "vcodec": "none", "acodec": "opus", "language": "en", "abr": 150},
    {"format_id": "a_unknown", "vcodec": "none", "acodec": "opus", "abr": 190},
]


def test_explicit_spanish_region_not_confused_with_generic():
    result = select_audio(FORMATS, "es-ES")
    assert result.format_id == "a_es_ES"
    assert result.verified


def test_latam_exact():
    assert select_audio(FORMATS, "es-419").format_id == "a_latam"


def test_spanish_general_uses_labelled_track():
    assert select_audio(FORMATS, "es").format_id == "a_latam"


def test_missing_language_is_not_silently_substituted():
    tracks = [f for f in FORMATS if f.get("language") != "es-ES"]
    assert select_audio(tracks, "es-ES").format_id is None
    assert select_audio([FORMATS[-1]], "es").format_id is None


def test_language_matching_boundaries():
    assert language_matches("en-US", "en")
    assert language_matches("es-419", "es")
    assert not language_matches("es-419", "es-ES")
    assert not language_matches("fr", "en")


def test_video_quality_cap():
    assert select_video(FORMATS, "best") == "v1080"
    assert select_video(FORMATS, "720") == "v720"
    assert select_video(FORMATS, "480") is None


def test_explicit_mux_prevents_accidental_audio_mix():
    args = download_args("https://www.youtube.com/watch?v=abcdefghijk", Path("C:/temp"),
                         "v1080", "a_es_ES", "best", 3)
    assert args[args.index("-f") + 1] == "v1080+a_es_ES"
    assert args[args.index("-o") + 1].startswith("003 - ")
    assert "--download-archive" in args
    assert "--recode-video" in args


def test_safe_names():
    assert safe_name('Season: 1 / Act?') == "Season_ 1 _ Act_"
    assert safe_name(" . ") == "Lista de reproducción"
    assert "%(title)" in output_template()


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/playlist?list=abc", True),
    ("https://youtu.be/abcdefghijk", True),
    ("https://evil.youtube.com.example.com/watch?v=x", False),
    ("file:///etc/passwd", False),
    ("https://youtube.com.evil.com", False),
])
def test_youtube_validation(url, expected):
    assert valid_youtube_url(url) is expected


def test_preferences_reject_invalid():
    with pytest.raises(ValueError):
        Preferences(language="bad").validate()
