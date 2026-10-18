import pytest

from cliptube import wclipboard
from cliptube.history import checkUrl


def test_checkUrl_accepts_bbc_sounds_radio_url():
    url = "https://www.bbc.co.uk/sounds/play/m001exmp"

    assert checkUrl(url) == url


def test_checkUrl_accepts_bbc_sounds_series_url():
    url = "https://www.bbc.co.uk/sounds/brand/m0024fk6"

    assert checkUrl(url) == url


def test_sortUrls_separates_content_types():
    urls = [
        "https://www.youtube.com/watch?v=video1",
        "https://www.youtube.com/playlist?list=abc123",
        "https://www.bbc.co.uk/iplayer/episodes/p09fs2qh/time?seriesId=p09fs2qh-structural-3-m00316gj",
        "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
        "https://www.bbc.co.uk/sounds/brand/m0024fk6",
        "https://www.bbc.co.uk/sounds/play/m001exmp",
        "https://youtu.be/video2",
    ]

    playlists, iplayer, radio, videos = wclipboard.sortUrls(urls)

    assert playlists == ["https://www.youtube.com/playlist?list=abc123"]
    assert iplayer == [
        "https://www.bbc.co.uk/iplayer/episodes/p09fs2qh/time?seriesId=p09fs2qh-structural-3-m00316gj",
        "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
    ]
    assert radio == [
        "https://www.bbc.co.uk/sounds/brand/m0024fk6",
        "https://www.bbc.co.uk/sounds/play/m001exmp",
    ]
    assert videos == [
        "https://www.youtube.com/watch?v=video1",
        "https://youtu.be/video2",
    ]


def test_processNewUrls_writes_bbc_pvrs_and_queues_video_urls(monkeypatch):
    queued = []
    written = []

    def fake_queue_urls(urls, vtype="v"):
        queued.append((urls, vtype))

    monkeypatch.setattr(wclipboard.localqueue, "queue_urls", fake_queue_urls)
    monkeypatch.setattr(wclipboard, "readConfig", lambda: _bbc_config(True))
    monkeypatch.setattr(wclipboard, "write_pvr_file", written.append)

    urls = [
        "https://www.youtube.com/watch?v=video1",
        "https://www.youtube.com/playlist?list=abc123",
        "https://www.bbc.co.uk/iplayer/episodes/p09fs2qh/time?seriesId=p09fs2qh-structural-3-m00316gj",
        "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
        "https://www.bbc.co.uk/sounds/brand/m0024fk6",
        "https://www.bbc.co.uk/sounds/play/m001exmp",
        "https://youtu.be/video2",
    ]
    wclipboard.processNewUrls(urls)

    assert queued == [
        (["https://www.youtube.com/watch?v=video1", "https://youtu.be/video2"], "v"),
        (["https://www.youtube.com/playlist?list=abc123"], "p"),
    ]
    assert written == [
        "https://www.bbc.co.uk/iplayer/episodes/p09fs2qh/time?seriesId=p09fs2qh-structural-3-m00316gj",
        "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
        "https://www.bbc.co.uk/sounds/brand/m0024fk6",
        "https://www.bbc.co.uk/sounds/play/m001exmp",
    ]


def test_processNewUrls_skips_bbc_when_disabled(monkeypatch):
    queued = []

    def fake_queue_urls(urls, vtype="v"):
        queued.append((urls, vtype))

    monkeypatch.setattr(wclipboard.localqueue, "queue_urls", fake_queue_urls)
    monkeypatch.setattr(wclipboard, "readConfig", lambda: _bbc_config(False))
    monkeypatch.setattr(wclipboard, "write_pvr_file", lambda url: pytest.fail(url))

    wclipboard.processNewUrls(
        [
            "https://www.youtube.com/watch?v=video1",
            "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
            "https://www.bbc.co.uk/sounds/play/m001example",
        ]
    )

    assert queued == [
        (["https://www.youtube.com/watch?v=video1"], "v"),
    ]


def _bbc_config(enabled):
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_dict({"bbc": {"enabled": str(enabled)}})
    return cfg


def test_checkForNewUrls_ignores_none(monkeypatch):
    called = {"processed": False}

    monkeypatch.setattr(wclipboard, "getNewUrls", lambda: None)

    def fake_process(urls):
        called["processed"] = True

    monkeypatch.setattr(wclipboard, "processNewUrls", fake_process)

    wclipboard.checkForNewUrls()

    assert called["processed"] is False


def test_checkForNewUrls_processes_non_empty(monkeypatch):
    new_urls = ["https://www.youtube.com/watch?v=video1"]
    processed = {"urls": None}

    monkeypatch.setattr(wclipboard, "getNewUrls", lambda: new_urls)

    def fake_process(urls):
        processed["urls"] = urls

    monkeypatch.setattr(wclipboard, "processNewUrls", fake_process)

    wclipboard.checkForNewUrls()

    assert processed["urls"] == new_urls
