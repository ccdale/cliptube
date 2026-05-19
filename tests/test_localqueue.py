#
# Copyright (c) 2023-2024, Chris Allison
#
#     This file is part of cliptube.
#
#     cliptube is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     cliptube is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cliptube.  If not, see <http://www.gnu.org/licenses/>.
#

"""Tests for the localqueue module."""

import json
from unittest.mock import patch

import cliptube.localqueue as localqueue
from cliptube.localqueue import (
    LocalQueueProcessor,
    ProcessingTask,
    get_merger_output_line,
)


def test_ProcessingTask():
    """Test ProcessingTask initialization and repr."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    task = ProcessingTask(url, vtype="v")
    assert task.url == url
    assert task.vtype == "v"
    assert "ProcessingTask" in repr(task)


def test_ProcessingTask_serialization():
    """Test ProcessingTask serialization and deserialization."""
    url = "https://www.youtube.com/watch?v=test123"
    task = ProcessingTask(url, vtype="p")

    # Serialize to dict
    task_dict = task.to_dict()
    assert task_dict["url"] == url
    assert task_dict["vtype"] == "p"

    # Deserialize from dict
    restored_task = ProcessingTask.from_dict(task_dict)
    assert restored_task.url == url
    assert restored_task.vtype == "p"


def test_ProcessingTask_vtype_variants():
    """Test ProcessingTask with different vtypes."""
    url = "https://example.com/video"
    for vtype in ["v", "p", "i"]:
        task = ProcessingTask(url, vtype=vtype)
        assert task.vtype == vtype


def test_LocalQueueProcessor_initialization():
    """Test that LocalQueueProcessor initializes correctly."""
    processor = LocalQueueProcessor(num_workers=1)
    assert processor.task_queue is not None
    assert len(processor.workers) == 1
    assert processor.workers[0].is_alive()
    processor.shutdown(timeout=2)


def test_LocalQueueProcessor_multiple_workers():
    """Test initialization with multiple workers."""
    processor = LocalQueueProcessor(num_workers=3)
    assert len(processor.workers) == 3
    for worker in processor.workers:
        assert worker.is_alive()
    processor.shutdown(timeout=2)


def test_queue_urls():
    """Test that URLs are queued without errors."""
    processor = LocalQueueProcessor(num_workers=1)
    urls = [
        "https://www.youtube.com/watch?v=test1",
        "https://www.youtube.com/watch?v=test2",
    ]
    # Mock shellCommand to avoid actual processing
    with patch("cliptube.localqueue.shellCommand") as mock_cmd:
        mock_cmd.return_value = ("", "")
        processor.queue_urls(urls, vtype="v")
        # Give the worker a moment to process
        processor.task_queue.join()
        assert processor.task_queue.empty()
    processor.shutdown(timeout=2)


def test_module_level_api_not_initialized():
    """Test that module-level API raises error if not initialized."""
    # Reset the global processor
    localqueue._processor = None
    try:
        localqueue.queue_urls(["https://example.com"])
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "not initialized" in str(e).lower()


def test_module_level_initialize_and_queue():
    """Test module-level initialize and queue_urls functions."""
    localqueue.initialize(num_workers=1)
    assert localqueue._processor is not None

    with patch("cliptube.localqueue.shellCommand") as mock_cmd:
        mock_cmd.return_value = ("", "")
        localqueue.queue_urls(["https://www.youtube.com/watch?v=test"], vtype="v")
        localqueue._processor.task_queue.join()

    localqueue.shutdown(timeout=2)
    assert localqueue._processor is None


def test_shutdown_drains_queue():
    """Test that shutdown waits for all tasks to complete."""
    processor = LocalQueueProcessor(num_workers=1)

    with patch("cliptube.localqueue.shellCommand") as mock_cmd:
        # Make commands take a moment
        mock_cmd.return_value = ("", "")
        urls = [f"https://example.com/video{i}" for i in range(3)]
        processor.queue_urls(urls, vtype="v")

        # Shutdown should wait for all to complete
        processor.shutdown(timeout=5)

        # All 3 tasks should have been processed
        assert mock_cmd.call_count >= 3


def test_processing_task_different_vtypes():
    """Test command selection by vtype with correct output handling."""
    videos = ["https://example.com/v1", "https://example.com/v2"]
    playlists = ["https://example.com/p1"]
    iplayer = ["https://example.com/i1"]

    processor = LocalQueueProcessor(num_workers=1, restore_from_cache=False)

    with (
        patch("cliptube.localqueue.shellCommand") as mock_cmd,
        patch("cliptube.localqueue.getYtDlpBin", return_value="/home/chris/bin/yt-dlp"),
    ):
        mock_cmd.return_value = ("", "")
        processor.queue_urls(videos, vtype="v")
        processor.queue_urls(playlists, vtype="p")
        processor.queue_urls(iplayer, vtype="i")

        processor.task_queue.join()

        # Should have been called once per URL
        assert mock_cmd.call_count >= 4

        called_cmds = [list(call.args[0]) for call in mock_cmd.call_args_list]
        assert ["/home/chris/bin/yt-dlp", "https://example.com/v1"] in called_cmds
        assert ["/home/chris/bin/yt-dlp", "https://example.com/v2"] in called_cmds
        assert [
            "/home/chris/bin/yt-dlp",
            "-o",
            "/mnt/nas/youtube/playlists/%(playlist_title)s/%(title)s.%(ext)s",
            "https://example.com/p1",
        ] in called_cmds
        assert ["get_iplayer", "--url", "https://example.com/i1"] in called_cmds

    processor.shutdown(timeout=2)


def test_queue_length_logs_empty_once_per_drain_cycle():
    """Test queue length logging suppresses repeated empty queue messages."""
    processor = LocalQueueProcessor(num_workers=1, restore_from_cache=False)

    with (
        patch("cliptube.localqueue.shellCommand") as mock_cmd,
        patch("cliptube.localqueue.log.info") as mock_log_info,
    ):
        mock_cmd.return_value = ("", "")

        processor.queue_urls(
            ["https://example.com/video1", "https://example.com/video2"], vtype="v"
        )
        processor.task_queue.join()

        queue_logs = [
            call.args[0]
            for call in mock_log_info.call_args_list
            if call.args and call.args[0].startswith("Queue length:")
        ]
        assert queue_logs == ["Queue length: 1", "Queue length: 0"]

        mock_log_info.reset_mock()

        processor.queue_urls(["https://example.com/video3"], vtype="v")
        processor.task_queue.join()

        queue_logs = [
            call.args[0]
            for call in mock_log_info.call_args_list
            if call.args and call.args[0].startswith("Queue length:")
        ]
        assert queue_logs == ["Queue length: 0"]

    processor.shutdown(timeout=2)


def test_get_merger_output_line_prefers_last_match():
    stdout = "line 1\n[Merger] First output\nline 3"
    stderr = "noise\n[Merger] Final output"
    assert get_merger_output_line(stdout, stderr) == "[Merger] Final output"


def test_successful_ytdlp_logs_merger_line():
    processor = LocalQueueProcessor(num_workers=1, restore_from_cache=False)

    with (
        patch("cliptube.localqueue.shellCommand") as mock_cmd,
        patch("cliptube.localqueue.getYtDlpBin", return_value="/home/chris/bin/yt-dlp"),
        patch("cliptube.localqueue.log.info") as mock_log_info,
    ):
        mock_cmd.return_value = (
            "",
            '[download] 100%\n[Merger] Merging formats into "/mnt/nas/youtube/videos/myvideo.mkv"',
        )
        processor.queue_urls(["https://example.com/v1"], vtype="v")
        processor.task_queue.join()

        info_messages = [call.args[0] for call in mock_log_info.call_args_list]
        assert "myvideo.mkv" in info_messages

    processor.shutdown(timeout=2)


def test_cache_save_and_load(monkeypatch, tmp_path):
    """Test saving pending tasks to cache and loading them on startup."""
    # Mock the cache path to use a temp directory
    cache_file = tmp_path / "test_queue.json"

    def mock_cache_path():
        return str(cache_file)

    monkeypatch.setattr("cliptube.localqueue.get_cache_path", mock_cache_path)

    # Create processor and queue some items
    processor = LocalQueueProcessor(num_workers=1, restore_from_cache=False)
    urls = [f"https://example.com/video{i}" for i in range(3)]
    processor.queue_urls(urls, vtype="v")

    # Shutdown without waiting to trigger cache save
    processor.shutdown(wait_for_current=False, timeout=1)

    # Verify cache file was created
    assert cache_file.exists()

    # Load and verify cached content
    with open(cache_file) as f:
        cached_data = json.load(f)
    assert len(cached_data) == 3
    for i, item in enumerate(cached_data):
        assert item["url"] == urls[i]
        assert item["vtype"] == "v"


def test_cache_restore_on_startup(monkeypatch, tmp_path):
    """Test that cached tasks are restored when processor starts."""
    cache_file = tmp_path / "test_queue.json"

    def mock_cache_path():
        return str(cache_file)

    monkeypatch.setattr("cliptube.localqueue.get_cache_path", mock_cache_path)

    # Create cache file with test data
    cached_tasks = [
        {"url": "https://example.com/cached1", "vtype": "v"},
        {"url": "https://example.com/cached2", "vtype": "p"},
    ]
    with open(cache_file, "w") as f:
        json.dump(cached_tasks, f)

    # Patch command execution before processor startup so restored tasks are mocked.
    with patch("cliptube.localqueue.shellCommand") as mock_cmd:
        mock_cmd.return_value = ("", "")

        # Create processor with restore enabled
        processor = LocalQueueProcessor(num_workers=1, restore_from_cache=True)

        # Verify tasks were loaded and processed
        processor.task_queue.join()

        # All 2 cached tasks should have been processed
        assert mock_cmd.call_count >= 2

        processor.shutdown(timeout=2)

    # Cache file should be deleted after loading
    assert not cache_file.exists()


def test_shutdown_with_wait_for_current_false():
    """Test fast shutdown that saves pending items without waiting."""
    processor = LocalQueueProcessor(num_workers=1)

    with patch("cliptube.localqueue.shellCommand") as mock_cmd:
        # Make commands slow
        import time

        def slow_command(*args, **kwargs):
            time.sleep(0.1)
            return ("", "")

        mock_cmd.side_effect = slow_command
        urls = [f"https://example.com/slow{i}" for i in range(5)]
        processor.queue_urls(urls, vtype="v")

        # Fast shutdown without waiting for all tasks
        processor.shutdown(wait_for_current=False, timeout=1)

        # Only some tasks should have been processed (not all 5)
        # The exact number depends on timing, but it should be less than 5
        assert mock_cmd.call_count < 5
