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

import sys
import threading
from queue import Queue

from cliptube import errorNotify, log
from cliptube.config import readConfig
from cliptube.files import getOutputFileName
from cliptube.shell import shellCommand


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


class URLProcessorWorker(threading.Thread):
    """Background worker thread that processes URLs from a queue."""

    def __init__(self, task_queue):
        """
        Initialize the worker thread.

        Args:
            task_queue: The Queue.Queue to pull tasks from
        """
        super().__init__(daemon=True)
        self.task_queue = task_queue
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
            cfg = readConfig()
            outdir = getOutputFileName(cfg, vtype=task.vtype)

            if task.vtype == "i":
                # iplayer processing
                cmd = ["get_iplayer", "--url", task.url, "-o", outdir]
            else:
                # yt-dlp for videos and playlists
                cmd = ["yt-dlp", "-o", outdir, task.url]

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

    def stop(self):
        """Signal the worker to stop."""
        self.running = False


class LocalQueueProcessor:
    """
    Manages a queue and worker thread(s) for local URL processing.
    """

    def __init__(self, num_workers=1):
        """
        Initialize the processor.

        Args:
            num_workers: Number of worker threads (default: 1, sequential processing)
        """
        self.task_queue = Queue()
        self.workers = []
        for _ in range(num_workers):
            worker = URLProcessorWorker(self.task_queue)
            worker.start()
            self.workers.append(worker)
        log.debug(f"Started {num_workers} URL processor worker(s)")

    def queue_urls(self, urls, vtype="v"):
        """
        Queue multiple URLs for processing.

        Args:
            urls: List of URL strings
            vtype: Type of content ('v', 'p', or 'i')
        """
        for url in urls:
            task = ProcessingTask(url, vtype=vtype)
            self.task_queue.put(task)
            log.debug(f"Queued: {task}")

    def shutdown(self, timeout=None):
        """
        Gracefully shut down, waiting for pending tasks to complete.

        Args:
            timeout: Maximum seconds to wait for tasks to finish
        """
        log.info("Waiting for queued tasks to complete...")
        self.task_queue.join()
        log.debug("All tasks complete, stopping workers...")
        for worker in self.workers:
            self.task_queue.put(None)  # Sentinel to signal worker to exit
            worker.stop()
        for worker in self.workers:
            worker.join(timeout=timeout)
        log.info("URL processor shut down complete")


# Global processor instance
_processor = None


def initialize(num_workers=1):
    """
    Initialize the global URL processor.

    Args:
        num_workers: Number of worker threads
    """
    global _processor
    if _processor is None:
        _processor = LocalQueueProcessor(num_workers=num_workers)
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


def shutdown(timeout=None):
    """
    Gracefully shut down the processor.

    Args:
        timeout: Maximum seconds to wait for pending tasks
    """
    global _processor
    if _processor is not None:
        _processor.shutdown(timeout=timeout)
        _processor = None
