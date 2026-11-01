import configparser
import json
import os
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

from cliptube import localqueue
from cliptube.history import HistoryStore
from cliptube.localqueue import LocalQueueProcessor, ProcessingTask


@pytest.fixture
def history(tmp_path):
    return HistoryStore(
        tmp_path / "history", legacy_list=tmp_path / "list",
        legacy_cache=tmp_path / "pending",
    )


def test_task_serialization():
    task = ProcessingTask("https://youtu.be/abc", "p")
    assert ProcessingTask.from_dict(task.to_dict()).to_dict() == task.to_dict()
    assert "ProcessingTask" in repr(task)
    assert ProcessingTask("https://bbc.co.uk/sounds/play/abc", "r").vtype == "b"


def test_queue_success_and_dedup(history):
    processor = LocalQueueProcessor(history=history)
    with patch("cliptube.localqueue.shellCommand", return_value=("", "")) as command:
        assert processor.queue_urls(["https://youtu.be/abc"] * 2) == 1
        processor.task_queue.join()
        assert processor.queue_urls(["https://youtu.be/abc"]) == 0
        assert command.call_count == 1
        assert history.records["https://youtu.be/abc"]["state"] == "done"
    processor.shutdown()


def test_failed_is_logged_and_not_retried(history):
    processor = LocalQueueProcessor(history=history)
    url = "https://youtu.be/fail"
    with (
        patch("cliptube.localqueue.shellCommand", side_effect=subprocess.CalledProcessError(7, ["yt-dlp"])),
        patch.object(localqueue.log, "error") as logged,
    ):
        processor.queue_urls([url])
        processor.task_queue.join()
        assert history.records[url]["state"] == "failed"
        assert history.records[url]["exitcode"] == 7
        assert url in logged.call_args.args[0]
        assert "exit code 7" in logged.call_args.args[0]
        processor.queue_urls([url])
        assert processor.task_queue.empty()
    processor.shutdown()


def test_playlist_command(history):
    processor = LocalQueueProcessor(history=history)
    with (
        patch("cliptube.localqueue.shellCommand", return_value=("", "")) as command,
        patch("cliptube.localqueue.getYtDlpBin", return_value="yt-dlp"),
    ):
        processor.queue_urls(["https://youtube.com/playlist?list=abc"], "p")
        processor.task_queue.join()
        assert command.call_args.args[0] == [
            "yt-dlp", "-o",
            "/mnt/nas/youtube/playlists/%(playlist_title)s/%(title)s.%(ext)s",
            "https://youtube.com/playlist?list=abc",
        ]
    processor.shutdown()


@pytest.mark.parametrize("enabled", [True, False])
def test_bbc_pvr_completion(history, tmp_path, enabled):
    cfg = configparser.ConfigParser()
    cfg.read_dict({"bbc": {"enabled": str(enabled), "pvrdir": str(tmp_path / "pvr")}})
    processor = LocalQueueProcessor(history=history)
    url = "https://www.bbc.co.uk/sounds/brand/m0024fk6"
    with patch("cliptube.localqueue.readConfig", return_value=cfg):
        processor.queue_urls([url], "b")
        processor.task_queue.join()
    assert history.records[url]["state"] == "done"
    assert (tmp_path / "pvr" / "m0024fk6").exists() == enabled
    if not enabled:
        assert history.records[url]["outcome"] == "disabled"
    processor.shutdown()


def test_invalid_pvr_is_failed(history):
    cfg = configparser.ConfigParser()
    processor = LocalQueueProcessor(history=history)
    url = "https://www.bbc.co.uk/sounds/unknown/abc"
    with patch("cliptube.localqueue.readConfig", return_value=cfg):
        processor.queue_urls([url], "b")
        processor.task_queue.join()
    assert history.records[url]["state"] == "failed"
    processor.shutdown()


def test_pending_and_running_restored_before_new_work(history):
    history.accept("https://youtu.be/queued")
    history.accept("https://youtu.be/running")
    history.transition("https://youtu.be/running", "running")
    history.accept("https://youtu.be/failed")
    history.transition("https://youtu.be/failed", "failed")
    processor = LocalQueueProcessor(num_workers=0, history=history)
    processor.queue_urls(["https://youtu.be/new"])
    tasks = [processor.task_queue.get_nowait().url for _ in range(3)]
    assert tasks == ["https://youtu.be/running", "https://youtu.be/queued", "https://youtu.be/new"]
    processor.shutdown()


def test_shutdown_preserves_pending_and_is_idempotent(history):
    processor = LocalQueueProcessor(num_workers=0, history=history)
    processor.queue_urls(["https://youtu.be/a", "https://youtu.be/b"])
    processor.shutdown()
    processor.shutdown()
    assert len(history.pending()) == 2
    with pytest.raises(RuntimeError, match="shutdown"):
        processor.queue_urls(["https://youtu.be/c"])


def test_shutdown_kills_sigterm_ignoring_group_and_restores(history, tmp_path):
    ready = tmp_path / "ready"
    child_pid = tmp_path / "child"
    child_code = (
        "import signal,time,pathlib,os; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    code = (
        "import signal,subprocess,sys,time,pathlib; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); "
        "time.sleep(60)"
    )
    processor = LocalQueueProcessor(history=history)
    original = localqueue.shellCommand
    processes = []

    def command(_cmd, process_callback):
        def remember(proc):
            processes.append(proc)
            process_callback(proc)
        return original([sys.executable, "-c", code], process_callback=remember)

    try:
        with patch("cliptube.localqueue.shellCommand", side_effect=command):
            processor.queue_urls(["https://youtu.be/running", "https://youtu.be/pending"])
            deadline = time.monotonic() + 5
            while not (ready.exists() and child_pid.exists()):
                assert time.monotonic() < deadline
                threading.Event().wait(0.01)
            started = time.monotonic()
            processor.shutdown()
            assert time.monotonic() - started < 4
            assert not processor.workers[0].is_alive()
            assert processes[0].returncode == -signal.SIGKILL
            assert history.records["https://youtu.be/running"]["state"] == "running"
            assert history.records["https://youtu.be/pending"]["state"] == "queued"
            stat = f"/proc/{child_pid.read_text()}/stat"
            if os.path.exists(stat):
                with open(stat) as stream:
                    assert stream.read().split()[2] == "Z"
            restored = LocalQueueProcessor(num_workers=0, history=history)
            assert restored.task_queue.qsize() == 2
            restored.shutdown()
    finally:
        processor.shutdown()
        for proc in processes:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_cache_migration_preserves_old_pending(tmp_path):
    old_list = tmp_path / "list"
    old_list.write_text("https://youtu.be/abc\nhttps://youtu.be/done\n")
    cache = tmp_path / "pending_queue.json"
    cache.write_text(json.dumps([{"url": "https://youtu.be/abc", "vtype": "v"}]))
    history = HistoryStore(tmp_path / "history", legacy_list=old_list, legacy_cache=cache)
    assert history.records["https://youtu.be/abc"]["state"] == "queued"
    assert history.records["https://youtu.be/done"]["state"] == "done"
    assert not cache.exists()
    assert old_list.exists()


def test_module_api(history, monkeypatch):
    monkeypatch.setattr(localqueue, "_processor", None)
    with pytest.raises(RuntimeError, match="not initialized"):
        localqueue.queue_urls(["https://youtu.be/abc"])
    localqueue.initialize(num_workers=0, history=history)
    localqueue.queue_urls(["https://youtu.be/abc"])
    localqueue.shutdown()
    assert localqueue._processor is None


def test_worker_persistence_failure_is_explicit_and_wakes_main(history):
    woken = threading.Event()
    processor = LocalQueueProcessor(history=history, on_failure=woken.set)
    try:
        with patch.object(history, "transition", side_effect=OSError("disk full")):
            processor.queue_urls(["https://youtu.be/abc"])
            assert woken.wait(2)
            assert processor.failed.is_set()
            assert history.records["https://youtu.be/abc"]["state"] == "queued"
    finally:
        processor.shutdown()


def test_stop_requested_before_process_registration_kills_new_child(history):
    processor = LocalQueueProcessor(num_workers=0, history=history)
    worker = localqueue.URLProcessorWorker(processor)
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    try:
        processor.stop_event.set()
        worker._store_process(proc)
        assert proc.wait(timeout=2) in {-signal.SIGTERM, -signal.SIGKILL}
    finally:
        processor.shutdown()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def test_sigterm_during_download_is_interrupted_not_failed(history):
    stop_event = threading.Event()
    processor = LocalQueueProcessor(history=history, stop_event=stop_event)

    def command(*args, **kwargs):
        stop_event.set()
        raise subprocess.CalledProcessError(-signal.SIGTERM, ["yt-dlp"])

    with patch("cliptube.localqueue.shellCommand", side_effect=command):
        processor.queue_urls(["https://youtu.be/abc"])
        processor.task_queue.join()
    assert history.records["https://youtu.be/abc"]["state"] == "running"
    processor.shutdown()


def test_merger_filename_logged(history):
    processor = LocalQueueProcessor(history=history)
    with (
        patch("cliptube.localqueue.shellCommand", return_value=(
            "", '[Merger] Merging formats into "/tmp/example.mkv"',
        )),
        patch.object(localqueue.log, "info") as logged,
    ):
        processor.queue_urls(["https://youtu.be/abc"])
        processor.task_queue.join()
        assert "example.mkv" in [call.args[0] for call in logged.call_args_list]
    processor.shutdown()
