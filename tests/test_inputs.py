import pytest

from youtube_smart_downloader.inputs import classify_url, parse_text_links
from youtube_smart_downloader.requests import DownloadRequest, TimeRange, parse_time_range


@pytest.mark.parametrize(
    "url,kind",
    [
        ("https://youtu.be/abcdefghijk?t=10", "video"),
        ("https://www.youtube.com/watch?v=abcdefghijk", "video"),
        ("https://m.youtube.com/shorts/abcdefghijk", "video"),
        ("https://www.youtube.com/live/abcdefghijk", "video"),
        ("https://www.youtube.com/embed/abcdefghijk", "video"),
        ("https://www.youtube.com/playlist?list=PL_test", "playlist"),
        ("https://www.youtube.com/watch?v=abcdefghijk&list=PL_test", "ambiguous"),
        ("https://youtu.be/abcdefghijk?list=PL_test", "ambiguous"),
    ],
)
def test_automatic_classification(url, kind):
    result = classify_url(url)
    assert result.kind == kind
    if kind in {"video", "ambiguous"}:
        assert result.video_url == "https://www.youtube.com/watch?v=abcdefghijk"
    if kind in {"playlist", "ambiguous"}:
        assert result.playlist_url == "https://www.youtube.com/playlist?list=PL_test"


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/123",
        "https://youtube.com.evil.com/watch?v=abcdefghijk",
        "https://www.youtube.com/@channel",
        "https://www.youtube.com/watch?v=short",
        "file:///video.mp4",
        "https://www.youtube.com/playlist",
        "",
    ],
)
def test_unsupported_inputs_are_rejected(url):
    with pytest.raises(ValueError):
        classify_url(url)


def test_txt_preserves_order_and_reports_line_numbers_and_duplicates():
    result = parse_text_links(
        "\ufeff# My links\n\nhttps://youtu.be/abcdefghijk\nhttps://www.youtube.com/watch?v=12345678901\nhttps://www.youtube.com/watch?v=abcdefghijk&t=5\ninvalid\nhttps://www.youtube.com/playlist?list=PL_x\nhttps://youtu.be/abcdefghijk?list=PL_x\n; comment\n] comment"
    )
    assert result.links == [
        "https://www.youtube.com/watch?v=abcdefghijk",
        "https://www.youtube.com/watch?v=12345678901",
    ]
    assert result.duplicates == ["Line 5: same video as line 3"]
    assert len(result.issues) == 3
    assert [issue.split(":")[0] for issue in result.issues] == ["Line 6", "Line 7", "Line 8"]


def test_empty_txt_does_not_create_a_queue():
    assert parse_text_links("# comment\n\n").links == []


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("", "", None),
        ("0", "", None),
        ("90", "180", TimeRange(90, 180)),
        ("01:30", "03:00", TimeRange(90, 180)),
        ("01:02:30", "", TimeRange(3750)),
        ("", "10", TimeRange(0, 10)),
    ],
)
def test_time_ranges(start, end, expected):
    assert parse_time_range(start, end) == expected


@pytest.mark.parametrize(
    "start,end",
    [
        ("-1", ""),
        ("1.5", ""),
        ("1:60", ""),
        ("60:00", ""),
        ("1:60:00", ""),
        ("1:2:3:4", ""),
        ("NaN", ""),
        ("1", "1"),
        ("2", "1"),
    ],
)
def test_invalid_ranges(start, end):
    with pytest.raises(ValueError):
        parse_time_range(start, end)


def test_txt_ranges_preserve_distinct_clips_and_normalize_duplicates():
    url = "https://youtu.be/abcdefghijk"
    result = parse_text_links(
        "\n".join(
            [
                url,
                f"{url};;",
                f" {url} ; 01:30 ; 03:00 ",
                f"{url};90;180",
                f"{url};90;",
                f"{url};;30",
                f"{url};bad;30",
                f"{url};10",
                f"{url};1;2;3",
            ]
        )
    )
    canonical = "https://www.youtube.com/watch?v=abcdefghijk"
    assert result.requests == [
        DownloadRequest(canonical),
        DownloadRequest(canonical, TimeRange(90, 180)),
        DownloadRequest(canonical, TimeRange(90)),
        DownloadRequest(canonical, TimeRange(0, 30)),
    ]
    assert len(result.duplicates) == 2
    assert [issue.split(":")[0] for issue in result.issues] == ["Line 7", "Line 8", "Line 9"]
