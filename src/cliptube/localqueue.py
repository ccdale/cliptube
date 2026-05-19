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

"""Local queue-based URL processor with background worker thread."""

import json
import os
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

from cliptube import errorNotify, log
from cliptube.config import expandPath, getYtDlpBin
from cliptube.shell import shellCommand


def get_cache_path():
    """Return the cache file path for pending queue items."""
    cache_dir = expandPath("~/.cache/cliptube")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    return os.path.join(cache_dir, "pending_queue.json")


class ProcessingTask:
    """Represents a single URL processing task."""

    def __init__(self, url, vtype="v"):
        """
        Initialize a processing task.

        Args:
            url: The URL to process
            vtype: Type of content ('v' for video, 'p' for playlist, 'i' for iplayer)
        """
        self.url = url
        self.vtype = vtype

    def __repr__(self):
        return f"ProcessingTask(url={self.url[:50]}..., vtype={self.vtype})"

    def to_dict(self):
        """Convert task to a dictionary for serialization."""
        return {"url": self.url, "vtype": self.vtype}

    @classmethod
    def from_dict(cls, data):
        """Create a task from a dictionary."""
        return cls(url=data["url"], vtype=data["vtype"])


class URLProcessorWorker(threading.Thread):
    """Background worker thread that processes URLs from a queue."""

    def __init__(self, task_queue, on_task_finished=None):
        """
        Initialize the worker thread.

        Args:
            task_queue: The Queue.Queue to pull tasks from
        """
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.on_task_finished = on_task_finished
        self.running = True

    def run(self):
        """Process tasks from the queue until stopped."""
        try:
            while self.running:
                try:
                    task = self.task_queue.get(timeout=1)
                    if task is None:  # Sentinel value for shutdown
                        break
                    self._process_task(task)
                except Empty:
                    # Queue timeout is expected - just continue waiting
                    continue
                except Exception as e:
                    if self.running:
                        errorNotify(sys.exc_info()[2], e)
        except Exception as e:
            errorNotify(sys.exc_info()[2], e)

    def _process_task(self, task):
        """
        Process a single task by running the appropriate command.

        Args:
            task: A ProcessingTask object
        """
        try:
            log.debug(f"Processing {task}")
            ytdlp_bin = getYtDlpBin()
            if task.vtype == "i":
                # iplayer processing
                cmd = ["get_iplayer", "--url", task.url]
            elif task.vtype == "p":
                # yt-dlp for playlists, organized by playlist name
                output_template = (
                    "/mnt/nas/youtube/playlists/%(playlist_title)s/%(title)s.%(ext)s"
                )
                cmd = [ytdlp_bin, "-o", output_template, task.url]
            else:
                # yt-dlp for videos
                cmd = [ytdlp_bin, task.url]

            log.info(f"Running command: {' '.join(cmd)}")
            sout, serr = shellCommand(cmd)
            log.debug(f"Command stdout: {sout}")
            if serr:
                log.warning(f"Command stderr: {serr}")
            log.info(f"Successfully processed {task.url}")
        except Exception as e:
            log.error(f"Failed to process {task.url}: {e}")
            errorNotify(sys.exc_info()[2], e)
        finally:
            self.task_queue.task_done()
            if self.on_task_finished is not None:
                self.on_task_finished()

    def stop(self):
        """Signal the worker to stop."""
        self.running = False


class LocalQueueProcessor:
    """
    Manages a queue and worker thread(s) for local URL processing.
    Supports cache persistence for unprocessed items on shutdown.
    """

    def __init__(self, num_workers=1, restore_from_cache=True):
        """
        Initialize the processor.

        Args:
            num_workers: Number of worker threads (default: 1, sequential processing)
            restore_from_cache: Whether to restore pending items from cache (default: True)
        """
        self.task_queue = Queue()
        self.cache_path = get_cache_path()
        self._queue_length_lock = threading.Lock()
        self._reported_empty_queue = False
        self.workers = []

        # Restore from cache if available and requested
        if restore_from_cache:
            self._load_from_cache()

        for _ in range(num_workers):
            worker = URLProcessorWorker(
                self.task_queue, on_task_finished=self._log_queue_length
            )
            worker.start()
            self.workers.append(worker)
        log.debug(f"Started {num_workers} URL processor worker(s)")

    def _log_queue_length(self):
        """Log pending queue length after a task finishes without spamming empty state."""
        queue_length = self.task_queue.qsize()
        with self._queue_length_lock:
            if queue_length == 0:
                if self._reported_empty_queue:
                    return
                self._reported_empty_queue = True
            else:
                self._reported_empty_queue = False
            log.info(f"Queue length: {queue_length}")

    def _load_from_cache(self):
        """Load pending tasks from cache if it exists."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    cached_tasks = json.load(f)
                count = 0
                for task_data in cached_tasks:
                    task = ProcessingTask.from_dict(task_data)
                    self.task_queue.put(task)
                    count += 1
                log.info(f"Restored {count} tasks from cache: {self.cache_path}")
                os.remove(self.cache_path)
            except Exception as e:
                log.error(f"Failed to restore tasks from cache: {e}")
                errorNotify(sys.exc_info()[2], e)

    def _save_to_cache(self):
        """Save pending tasks to cache for later recovery."""
        try:
            tasks = []
            # Drain the queue into a list
            while not self.task_queue.empty():
                try:
                    task = self.task_queue.get_nowait()
                    if task is not None:  # Skip sentinel values
                        tasks.append(task.to_dict())
                except Exception:
                    break

            if tasks:
                with open(self.cache_path, "w") as f:
                    json.dump(tasks, f, indent=2)
                log.info(f"Saved {len(tasks)} tasks to cache: {self.cache_path}")
            else:
                # Clean up empty cache file if it exists
                if os.path.exists(self.cache_path):
                    os.remove(self.cache_path)
        except Exception as e:
            log.error(f"Failed to save tasks to cache: {e}")
            errorNotify(sys.exc_info()[2], e)

    def queue_urls(self, urls, vtype="v"):
        """
        Queue multiple URLs for processing.

        Args:
            urls: List of URL strings
            vtype: Type of content ('v', 'p', or 'i')
        """
        if urls:
            with self._queue_length_lock:
                self._reported_empty_queue = False
        for url in urls:
            task = ProcessingTask(url, vtype=vtype)
            self.task_queue.put(task)
            log.debug(f"Queued: {task}")

    def shutdown(self, timeout=None, wait_for_current=True):
        """
        Gracefully shut down, allowing current job to finish then saving pending items.

        Args:
            timeout: Maximum seconds to wait for current task to finish
            wait_for_current: If True, wait for current job to finish before saving cache.
                              If False, save immediately (faster shutdown).
        """
        log.info("URL processor shutting down...")

        if wait_for_current:
            # Wait for the current job to finish (with timeout)
            log.info("Waiting for current task to complete...")
            self.task_queue.join()
            log.debug("Current task complete")
        else:
            log.debug(
                "Skipping wait for current task, saving pending items immediately"
            )

        # Save remaining tasks to cache
        self._save_to_cache()

        # Stop the workers
        log.debug("Stopping workers...")
        for worker in self.workers:
            self.task_queue.put(None)  # Sentinel to signal worker to exit
            worker.stop()
        for worker in self.workers:
            worker.join(timeout=timeout)
        log.info("URL processor shut down complete")


# Global processor instance
_processor = None


def initialize(num_workers=1, restore_from_cache=True):
    """
    Initialize the global URL processor.

    Args:
        num_workers: Number of worker threads
        restore_from_cache: Whether to restore pending items from cache on startup

    Returns:
        The initialized LocalQueueProcessor instance
    """
    global _processor
    if _processor is None:
        _processor = LocalQueueProcessor(
            num_workers=num_workers, restore_from_cache=restore_from_cache
        )
    return _processor


def queue_urls(urls, vtype="v"):
    """
    Queue URLs for local processing.

    Args:
        urls: List of URL strings
        vtype: Type of content ('v' for video, 'p' for playlist, 'i' for iplayer)

    Raises:
        RuntimeError: If processor not initialized
    """
    global _processor
    if _processor is None:
        raise RuntimeError("Processor not initialized. Call initialize() first.")
    _processor.queue_urls(urls, vtype=vtype)


def shutdown(timeout=None, wait_for_current=True):
    """
    Gracefully shut down the processor.

    Args:
        timeout: Maximum seconds to wait for current task to finish
        wait_for_current: If True, wait for current job to finish. If False, save immediately.
    """
    global _processor
    if _processor is not None:
        _processor.shutdown(timeout=timeout, wait_for_current=wait_for_current)
        _processor = None
