import configparser
import json
import os
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cliptube import wclipboard


def test_routing_keeps_bbc_out_of_ytdlp(monkeypatch):
    queued = Mock()
    monkeypatch.setattr(wclipboard.localqueue, "queue_urls", queued)
    video = "https://youtu.be/video"
    playlist = "https://youtube.com/playlist?list=abc"
    radio = "https://www.bbc.co.uk/sounds/brand/m0024fk6"
    tv = "https://www.bbc.co.uk/iplayer/episode/abcd1234/example"
    wclipboard.processNewUrls([video, playlist, radio, tv])
    assert queued.call_args_list[0].args == ([video],)
    assert queued.call_args_list[0].kwargs == {"vtype": "v"}
    assert queued.call_args_list[1].kwargs == {"vtype": "p"}
    assert queued.call_args_list[2].args == ([tv, radio],)
    assert queued.call_args_list[2].kwargs == {"vtype": "b"}


def test_queued_log_counts_only_accepted(monkeypatch):
    log = Mock()
    monkeypatch.setattr(wclipboard, "log", log)
    monkeypatch.setattr(wclipboard.localqueue, "queue_urls", lambda urls, vtype: 0)
    wclipboard.processNewUrls(["https://youtu.be/a", "https://youtu.be/b"])
    log.info.assert_not_called()
    monkeypatch.setattr(wclipboard.localqueue, "queue_urls", lambda urls, vtype: 1)
    wclipboard.processNewUrls(["https://youtu.be/a", "https://youtu.be/b"])
    log.info.assert_called_once_with("queued 1 video urls for processing")

def test_signal_handler_only_wakes_no_shutdown(monkeypatch):
    source = Mock()
    processor = Mock()
    monkeypatch.setattr(wclipboard, "source", source)
    monkeypatch.setattr(wclipboard, "processor", processor)
    wclipboard.ev.clear()
    wclipboard.interruptWP(wclipboard.SIGTERM, None)
    assert wclipboard.ev.is_set()
    source.wake.assert_called_once()
    processor.shutdown.assert_not_called()
    wclipboard.ev.clear()


@pytest.mark.parametrize("start_fails", [False, True])
def test_entry_point_stops_once_and_never_scans_after_sigterm(monkeypatch, start_fails):
    from cliptube import clipsource

    cfg = configparser.ConfigParser()
    fake_source = Mock()
    fake_processor = Mock()
    fake_processor.failed.is_set.return_value = False
    ledger = Mock()
    queued = []
    shutdown = Mock()
    fake_os = SimpleNamespace(
        path=SimpleNamespace(exists=lambda path: False),
        unlink=Mock(),
    )
    monkeypatch.setattr(wclipboard, "os", fake_os)
    monkeypatch.setattr(wclipboard, "signal", Mock())
    monkeypatch.setattr(wclipboard, "oneOnly", Mock())
    monkeypatch.setattr(wclipboard, "readConfig", lambda: cfg)
    monkeypatch.setattr(wclipboard, "HistoryStore", lambda **kwargs: ledger)
    monkeypatch.setattr(clipsource, "select_source", lambda cfg: fake_source)
    monkeypatch.setattr(wclipboard.localqueue, "initialize", lambda **kwargs: fake_processor)
    monkeypatch.setattr(wclipboard.localqueue, "shutdown", shutdown)
    monkeypatch.setattr(
        wclipboard.localqueue, "queue_urls",
        lambda urls, vtype: queued.append((urls, vtype)),
    )

    def next_clipboard(_timeout):
        if not queued:
            return "Copied https://youtu.be/abc"
        wclipboard.interruptWP(wclipboard.SIGTERM, None)
        return "https://youtu.be/must-not-queue"

    fake_source.wait_for_change.side_effect = next_clipboard
    if start_fails:
        fake_source.start.side_effect = RuntimeError("watcher failed")
        monkeypatch.setattr(wclipboard, "errorExit", Mock(side_effect=SystemExit(1)))
        with pytest.raises(SystemExit):
            wclipboard.watchClipboard()
        assert queued == []
    else:
        wclipboard.watchClipboard()
        assert queued == [(["https://youtu.be/abc"], "v")]
    shutdown.assert_called_once_with(timeout=3)
    fake_source.stop.assert_called_once()
    fake_processor.shutdown.assert_not_called()
    fake_os.unlink.assert_not_called()
    assert wclipboard.source is None
    assert wclipboard.processor is None
    wclipboard.ev.clear()


def test_real_sigterm_unblocks_watcher_and_persists_running_task(tmp_path):
    history_path = tmp_path / "history"
    ready = tmp_path / "ready"
    download_pid = tmp_path / "download_pid"
    child_code = (
        "import signal,time,pathlib,os;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"pathlib.Path({str(download_pid)!r}).write_text(str(os.getpid()));"
        f"pathlib.Path({str(ready)!r}).write_text('ready');"
        "time.sleep(60)"
    )
    service_code = f"""
import configparser, queue, sys
from types import SimpleNamespace
from cliptube import clipsource, localqueue, wclipboard
from cliptube.history import HistoryStore

class FakeSource:
    def __init__(self):
        self.changes = queue.SimpleQueue()
    def start(self):
        self.changes.put("https://youtu.be/interrupted")
    def wait_for_change(self, timeout):
        return self.changes.get(timeout=timeout)
    def wake(self):
        self.changes.put(None)
    def stop(self):
        self.wake()

cfg = configparser.ConfigParser()
wclipboard.readConfig = lambda: cfg
wclipboard.oneOnly = lambda path: None
wclipboard.os = SimpleNamespace(path=SimpleNamespace(exists=lambda path: False))
wclipboard.HistoryStore = lambda **kwargs: HistoryStore(
    {str(history_path)!r}, legacy_list={str(tmp_path / "oldlist")!r},
    legacy_cache={str(tmp_path / "cache")!r}
)
clipsource.select_source = lambda cfg: FakeSource()
original = localqueue.shellCommand
localqueue.shellCommand = lambda cmd, process_callback: original(
    [sys.executable, "-c", {child_code!r}], process_callback=process_callback
)
wclipboard.watchClipboard()
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", service_code], start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert proc.poll() is None
            assert time.monotonic() < deadline
            threading.Event().wait(0.01)
        started = time.monotonic()
        proc.terminate()
        out, err = proc.communicate(timeout=5)
        assert proc.returncode == 0, out + err
        assert time.monotonic() - started < 4
        records = [json.loads(line) for line in history_path.read_text().splitlines()]
        assert records[0]["state"] == "running"
        assert "will retry" in out + err
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        if download_pid.exists():
            try:
                os.killpg(int(download_pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
