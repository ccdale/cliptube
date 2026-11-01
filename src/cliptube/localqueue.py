"""Sequential downloads with durable task state and bounded process-group shutdown."""

import subprocess
import threading
import time
from pathlib import Path
from queue import Queue

from cliptube import log
from cliptube.config import (
    getBBCHandlingEnabled,
    getBBCPvrDirectory,
    getYtDlpBin,
    readConfig,
)
from cliptube.history import HistoryStore, task_type
from cliptube.pvr import write_pvr_file
from cliptube.shell import (
    getMergerOutputFilename,
    getMergerOutputLine,
    shellCommand,
    terminate_process_groups,
)


def get_merger_output_line(stdout, stderr):
    return getMergerOutputLine(stdout, stderr)


class ProcessingTask:
    def __init__(self, url, vtype="v"):
        self.url = url
        self.vtype = "b" if vtype in {"i", "r"} else vtype

    def __repr__(self):
        return f"ProcessingTask(url={self.url[:50]}..., vtype={self.vtype})"

    def to_dict(self):
        return {"url": self.url, "vtype": self.vtype}

    @classmethod
    def from_dict(cls, data):
        return cls(data["url"], data.get("vtype", task_type(data["url"])))


class URLProcessorWorker(threading.Thread):
    def __init__(self, processor):
        super().__init__(daemon=True)
        self.processor = processor
        self.current_task = None
        self.current_process = None

    def run(self):
        while True:
            task = self.processor.task_queue.get()
            try:
                if task is None:
                    return
                with self.processor.lock:
                    if self.processor.stop_requested():
                        return
                    self.current_task = task
                self._process_task(task)
            except Exception:  # noqa: BLE001
                # Persistence failures must stop processing, not silently lose state.
                log.exception("Worker stopped after an unexpected error")
                self.processor.failed.set()
                if self.processor.on_failure:
                    self.processor.on_failure()
                return
            finally:
                with self.processor.lock:
                    self.current_task = None
                    self.current_process = None
                self.processor.task_queue.task_done()
                self.processor._log_queue_length()

    def _store_process(self, proc):
        with self.processor.lock:
            self.current_process = proc
            stopping = self.processor.stop_requested()
        if stopping:
            terminate_process_groups([proc], grace=0)

    def _process_task(self, task):
        history = self.processor.history
        history.transition(task.url, "running")
        if self.processor.stop_requested():
            log.info(f"Interrupted {task.url}, will retry on restart")
            return
        title = None
        try:
            if task.vtype == "b":
                cfg = readConfig()
                if not getBBCHandlingEnabled(cfg):
                    log.info("BBC URL handling is disabled; skipping BBC URLs")
                    history.transition(task.url, "done", outcome="disabled")
                    return
                path = write_pvr_file(task.url, output_directory=getBBCPvrDirectory(cfg))
                log.info(f"Created get_iplayer PVR file: {path}")
            else:
                cmd = [getYtDlpBin()]
                if task.vtype == "p":
                    cmd.extend([
                        "-o", "/mnt/nas/youtube/playlists/%(playlist_title)s/%(title)s.%(ext)s",
                    ])
                cmd.append(task.url)
                log.info(f"Running command: {' '.join(cmd)}")
                sout, serr = shellCommand(cmd, process_callback=self._store_process)
                log.debug(f"Command stdout: {sout}")
                if serr:
                    log.warning(f"Command stderr: {serr}")
                filename = getMergerOutputFilename(sout, serr)
                if filename:
                    log.info(filename)
                    if task.vtype == "v":
                        title = Path(filename).stem
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            with self.processor.lock:
                interrupted = self.processor.stop_requested()
            if interrupted:
                log.info(f"Interrupted {task.url}, will retry on restart")
            else:
                code = getattr(exc, "returncode", None)
                log.error(f"Failed to process {task.url}: exit code {code}: {exc}")
                history.transition(task.url, "failed", error=str(exc), exitcode=code)
        else:
            with self.processor.lock:
                interrupted = self.processor.stop_requested()
            if interrupted:
                log.info(f"Interrupted {task.url}, will retry on restart")
            else:
                details = {"title": title} if title else {}
                history.transition(task.url, "done", **details)
                log.info(f"Successfully processed {task.url}")


class LocalQueueProcessor:
    def __init__(
        self, num_workers=1, restore_from_cache=True, history=None,
        on_failure=None, stop_event=None,
    ):
        self.task_queue = Queue()
        self.history = history if history is not None else HistoryStore()
        self.lock = threading.Lock()
        self.stopping = False
        self.closed = False
        self.failed = threading.Event()
        self.on_failure = on_failure
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self._queue_length_lock = threading.Lock()
        self._reported_empty_queue = False
        self.workers = []
        if restore_from_cache:
            for record in self.history.pending():
                self.task_queue.put(ProcessingTask.from_dict(record))
        for _ in range(num_workers):
            worker = URLProcessorWorker(self)
            self.workers.append(worker)
            worker.start()

    def _log_queue_length(self):
        length = self.task_queue.qsize()
        with self._queue_length_lock:
            if length == 0 and self._reported_empty_queue:
                return
            self._reported_empty_queue = length == 0
            log.info(f"Queue length: {length}")

    def queue_urls(self, urls, vtype="v"):
        with self.lock:
            if self.stop_requested():
                raise RuntimeError("Cannot queue work during shutdown")
            accepted = 0
            for url in urls:
                task = ProcessingTask(url, vtype)
                if self.history.accept(url, task.vtype):
                    self.task_queue.put(task)
                    self._reported_empty_queue = False
                    accepted += 1
            return accepted

    def stop_requested(self):
        return self.stopping or self.stop_event.is_set()

    def interrupt_all(self):
        with self.lock:
            processes = [
                worker.current_process for worker in self.workers
                if worker.current_process is not None
            ]
        terminate_process_groups(processes)

    def shutdown(self, timeout=5, wait_for_current=False, force=True):
        """Stop once, preserving pending/running entries already on disk.

        Legacy wait/force arguments remain accepted; shutdown never drains work.
        """
        with self.lock:
            if self.closed:
                return
            self.stopping = True
            self.stop_event.set()
            self.closed = True
        self.interrupt_all()
        for _ in self.workers:
            self.task_queue.put(None)
        deadline = time.monotonic() + (5 if timeout is None else timeout)
        for worker in self.workers:
            worker.join(max(0, deadline - time.monotonic()))
            if worker.is_alive():
                log.error(f"Worker {worker.name} did not stop within the shutdown deadline")
        log.info("URL processor shut down; unfinished tasks retained in history")


_processor = None


def initialize(
    num_workers=1, restore_from_cache=True, history=None, on_failure=None, stop_event=None,
):
    global _processor
    if _processor is None:
        _processor = LocalQueueProcessor(
            num_workers, restore_from_cache, history, on_failure, stop_event
        )
    return _processor


def queue_urls(urls, vtype="v"):
    if _processor is None:
        raise RuntimeError("Processor not initialized. Call initialize() first.")
    return _processor.queue_urls(urls, vtype)


def shutdown(timeout=5, wait_for_current=False):
    global _processor
    if _processor is not None:
        _processor.shutdown(timeout=timeout)
        _processor = None
