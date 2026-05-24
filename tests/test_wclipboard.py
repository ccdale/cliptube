from cliptube import wclipboard


def test_sortUrls_separates_content_types():
    urls = [
        "https://www.youtube.com/watch?v=video1",
        "https://www.youtube.com/playlist?list=abc123",
        "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
        "https://youtu.be/video2",
    ]

    playlists, iplayer, videos = wclipboard.sortUrls(urls)

    assert playlists == ["https://www.youtube.com/playlist?list=abc123"]
    assert iplayer == ["https://www.bbc.co.uk/iplayer/episode/b0000001/example"]
    assert videos == [
        "https://www.youtube.com/watch?v=video1",
        "https://youtu.be/video2",
    ]


def test_processNewUrls_routes_to_expected_queues(monkeypatch):
    queued = []

    def fake_queue_urls(urls, vtype="v"):
        queued.append((urls, vtype))

    monkeypatch.setattr(wclipboard.localqueue, "queue_urls", fake_queue_urls)

    urls = [
        "https://www.youtube.com/watch?v=video1",
        "https://www.youtube.com/playlist?list=abc123",
        "https://www.bbc.co.uk/iplayer/episode/b0000001/example",
        "https://youtu.be/video2",
    ]
    wclipboard.processNewUrls(urls)

    assert queued == [
        (["https://www.youtube.com/watch?v=video1", "https://youtu.be/video2"], "v"),
        (["https://www.youtube.com/playlist?list=abc123"], "p"),
        (["https://www.bbc.co.uk/iplayer/episode/b0000001/example"], "i"),
    ]


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
