import pytest

from cliptube.pvr import (
    BBCProgramme,
    is_bbc_programme_url,
    parse_bbc_url,
    write_pvr_file,
)


@pytest.mark.parametrize(
    ("url", "programme", "expected_text"),
    [
        (
            "https://www.bbc.co.uk/iplayer/episodes/p09fs2qh/time"
            "?seriesId=p09fs2qh-structural-3-m00316gj",
            BBCProgramme("p09fs2qh", "tv", True),
            "pid p09fs2qh\npidrecursive 1\ntype tv\n",
        ),
        (
            "https://www.bbc.co.uk/iplayer/episode/"
            "m00316gl/time-series-3-episode-1",
            BBCProgramme("m00316gl", "tv", False),
            "pid m00316gl\ntype tv\n",
        ),
        (
            "https://www.bbc.co.uk/sounds/brand/m0024fk6",
            BBCProgramme("m0024fk6", "radio", True),
            "pid m0024fk6\npidrecursive 1\ntype radio\n",
        ),
        (
            "https://www.bbc.co.uk/sounds/play/m0030x8z",
            BBCProgramme("m0030x8z", "radio", False),
            "pid m0030x8z\ntype radio\n",
        ),
    ],
)
def test_parse_bbc_url(url, programme, expected_text):
    actual = parse_bbc_url(url)

    assert actual == programme
    assert actual.to_pvr_text() == expected_text
    assert "Series 3" not in actual.to_pvr_text()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/iplayer/episode/m00316gl/title",
        "https://www.bbc.co.uk/iplayer/programme/m00316gl",
        "https://www.bbc.co.uk/sounds/episode/m0030x8z",
    ],
)
def test_parse_bbc_url_rejects_unsupported_urls(url):
    with pytest.raises(ValueError, match="Unsupported BBC URL"):
        parse_bbc_url(url)


def test_parse_bbc_url_accepts_different_pid_lengths():
    programme = parse_bbc_url("https://www.bbc.co.uk/sounds/play/m0030x8z123")

    assert programme == BBCProgramme("m0030x8z123", "radio", False)


def test_is_bbc_programme_url_accepts_unknown_programme_path():
    url = "https://www.bbc.co.uk/iplayer/collections/new-format/abc123"

    assert is_bbc_programme_url(url)
    with pytest.raises(ValueError, match="Unsupported BBC URL"):
        parse_bbc_url(url)


def test_write_pvr_file_creates_file(tmp_path):
    pvr_path = write_pvr_file(
        "https://www.bbc.co.uk/iplayer/episode/m00316gl/time-series-3-episode-1",
        output_directory=tmp_path,
    )

    assert pvr_path == tmp_path / "m00316gl"
    assert pvr_path.read_text(encoding="utf-8") == "pid m00316gl\ntype tv\n"