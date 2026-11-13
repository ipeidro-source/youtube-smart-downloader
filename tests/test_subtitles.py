import pytest

from youtube_smart_downloader.subtitles import clip_subrip


def test_clips_both_boundaries_and_preserves_text():
    source = (
        "1\n00:00:00,000 --> 00:00:00,500\nBefore\n\n"
        "2\n00:00:00,500 --> 00:00:01,500\nCross start\nSecond line\n\n"
        "3\n00:00:01,500 --> 00:00:02,500\nCross end\n\n"
        "4\n00:00:02,500 --> 00:00:03,000\nAfter\n"
    )
    assert clip_subrip(source, 1, 2) == (
        "1\n00:00:00,000 --> 00:00:00,500\nCross start\nSecond line\n\n"
        "2\n00:00:00,500 --> 00:00:01,000\nCross end\n"
    )


def test_no_overlapping_cues_and_open_end():
    source = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    assert clip_subrip(source, 1, 2) == ""
    assert clip_subrip(source, 0, None) == source


def test_invalid_timing_fails_instead_of_silently_publishing():
    with pytest.raises(ValueError, match="timing"):
        clip_subrip("1\ninvalid --> invalid\nHello\n", 1, 2)
