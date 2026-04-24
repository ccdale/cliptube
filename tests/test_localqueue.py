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

from unittest.mock import patch

import cliptube.localqueue as localqueue
from cliptube.localqueue import LocalQueueProcessor, ProcessingTask


def test_ProcessingTask():
    """Test ProcessingTask initialization and repr."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    task = ProcessingTask(url, vtype="v")
    assert task.url == url
    assert task.vtype == "v"
    assert "ProcessingTask" in repr(task)


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
    """Test that different vtypes are preserved in tasks."""
    videos = ["https://example.com/v1", "https://example.com/v2"]
    playlists = ["https://example.com/p1"]
    iplayer = ["https://example.com/i1"]

    processor = LocalQueueProcessor(num_workers=1)

    with patch("cliptube.localqueue.shellCommand") as mock_cmd:
        mock_cmd.return_value = ("", "")
        processor.queue_urls(videos, vtype="v")
        processor.queue_urls(playlists, vtype="p")
        processor.queue_urls(iplayer, vtype="i")

        processor.task_queue.join()

        # Should have been called once per URL
        assert mock_cmd.call_count >= 4

    processor.shutdown(timeout=2)
