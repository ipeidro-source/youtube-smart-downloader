"""Resolve requested languages before downloading any media."""

import copy

import pytest

from youtube_smart_downloader.core import Preferences, download_args, resolve_tracks
from youtube_smart_downloader.settings import normalize


def metadata():
    return {
        "formats": [
            {
                "format_id": "es-low",
                "vcodec": "none",
                "acodec": "aac",
                "language": "es-ES",
                "abr": 64,
            },
            {"format_id": "es", "vcodec": "none", "acodec": "aac", "language": "es-ES", "abr": 128},
            {
                "format_id": "en",
                "vcodec": "none",
                "acodec": "aac",
                "language": "en",
                "format_note": "English (original)",
            },
        ],
        "subtitles": {"es": [{"url": "https://example.org/manual", "ext": "vtt"}]},
        "automatic_captions": {
            "es": [{"url": "https://example.org/auto-es", "ext": "vtt"}],
            "en": [{"url": "https://example.org/auto-en", "ext": "vtt"}],
            "live_chat": [{"url": "https://example.org/chat", "ext": "json"}],
        },
    }


def test_deduplicates_formats_and_preserves_requested_default():
    plan = resolve_tracks(
        metadata(),
        Preferences(audio_languages=("original", "es", "en", "es-ES"), default_audio="en"),
    )
    assert [a.format_id for a in plan.audios] == ["en", "es"]
    assert plan.default_index == 0
    assert plan.container == "mkv"
    assert not plan.missing_audio


def test_partial_audio_and_subtitles_prefer_manual():
    plan = resolve_tracks(
        metadata(),
        Preferences(
            audio_languages=("es", "fr"),
            default_audio="fr",
            subtitle_languages=("es", "en", "fr"),
            automatic_subtitles=True,
        ),
    )
    assert [a.format_id for a in plan.audios] == ["es"]
    assert plan.missing_audio == ("fr",)
    assert plan.default_index == 0 and plan.container == "mkv"
    assert [(s["language"], s["source"]) for s in plan.subtitles] == [
        ("es", "subtitles"),
        ("en", "automatic_captions"),
    ]
    assert plan.missing_subtitles == ("fr",)


def test_automatic_subtitles_are_opt_in_and_regions_remain_strict():
    plan = resolve_tracks(
        metadata(), Preferences(audio_languages=("es-419",), subtitle_languages=("en",))
    )
    assert not plan.audios and not plan.subtitles
    assert plan.missing_audio == ("es-419",)
    assert plan.missing_subtitles == ("en",)


def test_fallback_only_when_no_audio_resolved():
    plan = resolve_tracks(metadata(), Preferences(audio_languages=("fr",), missing="fallback"))
    assert plan.fallback and plan.audios[0].format_id == "en"
    plan = resolve_tracks(metadata(), Preferences(audio_languages=("es", "fr"), missing="fallback"))
    assert not plan.fallback and len(plan.audios) == 1


def test_does_not_modify_source_metadata():
    source = metadata()
    original = copy.deepcopy(source)
    resolve_tracks(source, Preferences(audio_languages=("es",), subtitle_languages=("es",)))
    assert source == original


def test_migrate_settings_and_sanitize_new_values():
    migrated = normalize({"language": "en", "missing": "fallback"})
    assert migrated["audio_languages"] == ["en"]
    assert migrated["default_audio"] == "en"
    assert migrated["subtitle_languages"] == ["es", "en"]
    assert migrated["missing"] == "fallback"
    normalized = normalize(
        {
            "audio_languages": [None, {}, "es", "es", "fr"],
            "subtitle_languages": ["auto", "live_chat", "en"],
            "default_audio": "en",
            "container": [],
            "automatic_subtitles": "true",
        }
    )
    assert normalized["audio_languages"] == ["es", "fr"]
    assert normalized["subtitle_languages"] == ["en"]
    assert normalized["default_audio"] == "es"
    assert normalized["container"] == "mkv"
    assert normalized["automatic_subtitles"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"audio_languages": ()},
        {"audio_languages": ("../../bad",)},
        {"subtitle_languages": ("live_chat",)},
        {"container": "avi"},
        {"audio_languages": ("en",), "default_audio": "es"},
    ],
)
def test_invalid_preferences(kwargs):
    with pytest.raises(ValueError):
        Preferences(**kwargs).validate()


def test_explicit_multistream_arguments(tmp_path):
    args = download_args(
        "unused",
        tmp_path,
        "video",
        "es",
        "best",
        None,
        audio_ids=("es", "en"),
        container="mkv",
        copy_streams=True,
    )
    assert args[args.index("-f") + 1] == "video+es+en"
    assert "--audio-multistreams" in args
    assert args[args.index("--merge-output-format") + 1] == "mkv"
    assert "--recode-video" not in args


@pytest.mark.parametrize("container", ["mkv", "mp4"])
@pytest.mark.parametrize("languages", [("es",), ("es", "en")])
def test_container_selection_does_not_depend_on_audio_count(container, languages):
    plan = resolve_tracks(metadata(), Preferences(audio_languages=languages, container=container))
    assert len(plan.audios) == len(languages)
    assert plan.container == container
