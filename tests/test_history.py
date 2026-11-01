import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from cliptube.history import HistoryStore, extract_urls


def store(tmp_path, **kwargs):
    return HistoryStore(
        tmp_path / "history", legacy_list=tmp_path / "list",
        legacy_cache=tmp_path / "pending", **kwargs,
    )


def test_extract_urls_normalizes_and_deduplicates():
    assert extract_urls(
        "Copied: https://www.youtube.com/watch?v=abc&t=100\n"
        "https://www.youtube.com/watch?v=abc\nhttps://evil.youtube.com/watch?v=x"
    ) == ["https://www.youtube.com/watch?v=abc"]


def test_transitions_persist_and_reassertions_are_ignored(tmp_path):
    history = store(tmp_path)
    url = "https://youtu.be/abc"
    assert history.accept(url)
    for state in ["running", "failed"]:
        history.transition(url, state)
        assert not history.accept(url)
        assert store(tmp_path).records[url]["state"] == state
    assert store(tmp_path).pending() == []


def test_atomic_write_failure_preserves_old_history(tmp_path):
    history = store(tmp_path)
    history.accept("https://youtu.be/abc")
    original = history.path.read_bytes()
    with (
        patch("cliptube.history.os.replace", side_effect=OSError("disk failure")),
        pytest.raises(OSError, match="disk failure"),
    ):
        history.transition("https://youtu.be/abc", "done")
    assert history.path.read_bytes() == original
    assert history.records["https://youtu.be/abc"]["state"] == "queued"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["history"]


def test_prunes_only_old_done_entries(tmp_path):
    history = store(tmp_path)
    old = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    for state in ["done", "running", "queued", "failed"]:
        url = f"https://youtu.be/{state}"
        history.accept(url)
        if state != "queued":
            history.transition(url, state)
        history.records[url]["updated"] = old
    history._write(history.records)
    restored = store(tmp_path)
    assert set(restored.records) == {
        "https://youtu.be/running", "https://youtu.be/queued", "https://youtu.be/failed",
    }


def test_corrupt_history_fails_explicitly_without_overwriting(tmp_path):
    path = tmp_path / "history"
    path.write_text(json.dumps({"url": "abc", "state": "wrong"}) + "\n")
    with pytest.raises(ValueError, match="Invalid history record"):
        store(tmp_path)
    assert "wrong" in path.read_text()


def test_concurrent_accepts_and_updates_do_not_lose_records(tmp_path):
    history = store(tmp_path)

    def record(index):
        url = f"https://youtu.be/{index}"
        history.accept(url)
        history.transition(url, "running")
        history.transition(url, "done")

    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(record, range(20)))
    restored = store(tmp_path)
    assert len(restored.records) == 20
    assert all(record["state"] == "done" for record in restored.records.values())
