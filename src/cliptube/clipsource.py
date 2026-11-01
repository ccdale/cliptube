"""Blocking clipboard sources with bounded, process-group-aware shutdown.

Sources deliver plain text, not URLs: filtering and persistent de-duplication
belong to the consumer. Start once, then wait until stop; None means a timeout
or shutdown. Event backends fall back to live polling after failure.
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import time

from cliptube import log
from cliptube.config import (
    expandPath,
    getClipboardSettings,
    getClipboardSleepTime,
    readConfig,
)
from cliptube.shell import terminate_process_groups

# A Python callback preserves newlines, trailing whitespace and embedded NULs.
_WATCH_HELPER = (
    "import sys;"
    "data=sys.stdin.buffer.read();"
    "sys.stdout.buffer.write(len(data).to_bytes(8,'big')+data);"
    "sys.stdout.buffer.flush()"
)
_STOP = object()


def _selections(selection):
    return ("clipboard", "primary") if selection == "both" else (selection,)


def _terminate_groups(processes, grace):
    """Kill surviving descendants even when their session leader already exited."""
    terminate_process_groups(processes, grace=grace)
    for process in processes:
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass


def _reader_tool(environ=None, which=None):
    environ = os.environ if environ is None else environ
    which = shutil.which if which is None else which
    if environ.get("WAYLAND_DISPLAY") and which("wl-paste"):
        return "wl-paste"
    if environ.get("DISPLAY"):
        for tool in ("xclip", "xsel"):
            if which(tool):
                return tool
    # An explicitly configured poll backend can work with tools that have their
    # own display defaults, even without a session variable.
    for tool in ("wl-paste", "xclip", "xsel"):
        if which(tool):
            return tool
    return None


def _read_command(tool, selection):
    if tool == "wl-paste":
        return ["wl-paste", "--no-newline", "--type", "text"] + (
            ["--primary"] if selection == "primary" else []
        )
    if tool == "xclip":
        return ["xclip", "-o", "-selection", selection]
    if tool == "xsel":
        return ["xsel", "--output", "--primary" if selection == "primary" else "--clipboard"]
    raise ValueError(f"Unknown clipboard reader: {tool}")


def wayland_watch_support(timeout=1.0):
    """Return (supported, reason) by briefly running ``wl-paste --watch``.

    Compositors without the data-control protocol (e.g. GNOME/Mutter) make
    wl-paste exit immediately; a supported watcher keeps running.
    """
    try:
        process = subprocess.Popen(
            ["wl-paste", "--watch", "true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return False, str(exc)
    try:
        _, diagnostics = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_groups([process], 0.5)
        process.stderr.close()
        return True, ""
    detail = diagnostics.decode("utf-8", errors="replace").strip()
    return False, (
        f"wl-paste --watch exited with status {process.returncode}: "
        f"{detail or 'no stderr'}"
    )


def _gnome_history_available(cfg):
    try:
        return os.path.exists(expandPath(cfg["gnomeclipindicator"]["histfile"]))
    except KeyError:
        return False


class ClipSource:
    """Single-use source; stop is idempotent and releases blocked consumers."""

    def __init__(self, selection="clipboard", sleeptime=1.0, *, grace=0.5):
        if selection not in {"clipboard", "primary", "both"}:
            raise ValueError("selection must be clipboard, primary or both")
        if not 0 < sleeptime < float("inf"):
            raise ValueError("sleeptime must be finite and positive")
        self.selection = selection
        self.sleeptime = sleeptime
        self.grace = grace
        # SimpleQueue.put is reentrant on CPython, including signal handlers.
        self._queue = queue.SimpleQueue()
        self._stopped = threading.Event()
        self._lock = threading.RLock()
        self._processes = set()
        self._threads = []
        self._started = False
        self._cleaned = False
        self._fallback_started = False
        self._read_failures = set()

    def start(self):
        with self._lock:
            if self._stopped.is_set():
                raise RuntimeError("a stopped clipboard source cannot be restarted")
            if self._started:
                return
            self._started = True
            self._start()

    def _start(self):
        raise NotImplementedError

    def _thread(self, target, *args):
        with self._lock:
            if self._stopped.is_set():
                return
            thread = threading.Thread(target=target, args=args, daemon=True)
            self._threads.append(thread)
            thread.start()

    def _spawn(self, command, *, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL):
        with self._lock:
            if self._stopped.is_set():
                return None
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            self._processes.add(process)
            return process

    def _release(self, process):
        if process is None:
            return
        _terminate_groups([process], self.grace)
        with self._lock:
            self._processes.discard(process)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    def request_stop(self):
        """Signal-handler path: no source locks, child waits or thread joins."""
        self._stopped.set()
        self._queue.put(_STOP)

    def wake(self):
        """Unblock the consumer without doing synchronous cleanup."""
        self.request_stop()

    def stop(self):
        with self._lock:
            if self._cleaned:
                return
            self._cleaned = True
            self.request_stop()
            processes = list(self._processes)
            threads = list(self._threads)
        _terminate_groups(processes, self.grace)
        deadline = time.monotonic() + 1.0
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))

    def wait_for_change(self, timeout=None) -> str | None:
        if self._stopped.is_set():
            return None
        try:
            value = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if value is _STOP or self._stopped.is_set():
            # Keep a sentinel available for multiple consumers.
            self._queue.put(_STOP)
            return None
        return value

    def _emit(self, text):
        if not self._stopped.is_set() and text is not None:
            self._queue.put(text)

    def _emit_changed(self, last, key, text):
        # Polling sources re-read unchanged content; only report actual changes.
        if text is not None and last.get(key) != text:
            last[key] = text
            self._emit(text)

    def _read(self, tool, selection):
        process = None
        key = (tool, selection)
        try:
            process = self._spawn(_read_command(tool, selection), stderr=subprocess.PIPE)
            if process is None:
                return None
            data, diagnostics = process.communicate(timeout=2.0)
            detail = diagnostics.decode("utf-8", errors="replace").strip()
            if process.returncode == 0:
                self._read_failures.discard(key)
                if detail and not self._stopped.is_set():
                    log.debug(f"Clipboard reader {tool} ({selection}): {detail}")
                return data.decode("utf-8", errors="replace")
            # Known reader messages for an absent/non-text selection are normal.
            normal = any(message in detail.lower() for message in (
                "no selection", "no suitable type", "nothing is copied",
                "target string not available", "target utf8_string not available",
            ))
            if normal:
                self._read_failures.discard(key)
                if not self._stopped.is_set():
                    log.debug(f"Clipboard reader {tool} ({selection}): {detail}")
            else:
                self._read_error(key, f"exit status {process.returncode}: {detail or 'no stderr'}")
        except subprocess.TimeoutExpired as exc:
            # communicate preserves partial stderr on its timeout exception.
            detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            self._read_error(key, f"timed out after 2 seconds: {detail or 'no stderr'}")
        except OSError as exc:
            self._read_error(key, str(exc))
        finally:
            self._release(process)
        return None

    def _read_error(self, key, detail):
        if self._stopped.is_set():
            return
        tool, selection = key
        message = f"Clipboard reader {tool} ({selection}) failed: {detail}"
        if key not in self._read_failures:
            self._read_failures.add(key)
            log.warning(message)
        else:
            log.debug(message)

    def _poll(self, tool):
        last = {}
        while not self._stopped.is_set():
            for selection in _selections(self.selection):
                self._emit_changed(last, selection, self._read(tool, selection))
            self._stopped.wait(self.sleeptime)

    def _fallback(self, reason, tool):
        with self._lock:
            if self._fallback_started or self._stopped.is_set():
                return
            self._fallback_started = True
        log.warning(f"Clipboard watcher failed ({reason}); falling back to poll")
        # Stop the other selection watcher too, leaving no half-working backend.
        with self._lock:
            processes = list(self._processes)
        _terminate_groups(processes, self.grace)
        if self._stopped.wait(0.2):
            return
        if tool is None:
            log.warning("No live clipboard reader is available for fallback")
            return
        self._thread(self._poll, tool)


class GnomeHistorySource(ClipSource):
    """Poll the existing extension-history reader; selection is ignored."""

    def __init__(self, sleeptime=5.0, *, reader=None, cfg=None, **kwargs):
        super().__init__(sleeptime=sleeptime, **kwargs)
        self.reader = reader
        self.cfg = cfg

    def _start(self):
        self._thread(self._watch)

    def _watch(self):
        if self.reader is None:
            from cliptube.history import readGnomeClipIndicatorFile

            self.reader = lambda: readGnomeClipIndicatorFile(self.cfg)
        last = {}
        while not self._stopped.is_set():
            try:
                self._emit_changed(last, "history", "\n".join(self.reader() or []))
            except (OSError, ValueError, TypeError) as exc:
                log.warning(f"GNOME clipboard history read failed: {exc}")
            self._stopped.wait(self.sleeptime)


class PollSource(ClipSource):
    def __init__(self, tool=None, **kwargs):
        super().__init__(**kwargs)
        self.tool = tool or _reader_tool()
        if self.tool is None:
            raise ValueError("No live clipboard reader is available")

    def _start(self):
        self._thread(self._poll, self.tool)


class WaylandWatchSource(ClipSource):
    def _start(self):
        for selection in _selections(self.selection):
            self._thread(self._watch, selection)

    def _watch(self, selection):
        process = None
        try:
            command = ["wl-paste", "--no-newline", "--type", "text"]
            if selection == "primary":
                command.append("--primary")
            command.extend(["--watch", sys.executable, "-c", _WATCH_HELPER])
            process = self._spawn(command)
            if process is None:
                return
            # A helper can retain stdout after the watcher leader dies. Waiting
            # for the leader separately lets fallback kill that inherited pipe.
            self._thread(self._monitor, process)
            while not self._stopped.is_set():
                header = process.stdout.read(8)
                if not header:
                    break
                if len(header) != 8:
                    raise ValueError("truncated clipboard frame header")
                length = int.from_bytes(header, "big")
                if length > 64 * 1024 * 1024:
                    raise ValueError("clipboard frame exceeds 64 MiB")
                data = process.stdout.read(length)
                if len(data) != length:
                    raise ValueError("truncated clipboard frame")
                self._emit(data.decode("utf-8", errors="replace"))
            if not self._stopped.is_set():
                self._fallback("wl-paste exited or closed its output", "wl-paste")
        except (OSError, ValueError) as exc:
            self._fallback(str(exc), "wl-paste")
        finally:
            self._release(process)

    def _monitor(self, process):
        code = process.wait()
        if not self._stopped.is_set():
            self._fallback(f"wl-paste exited with status {code}", "wl-paste")


class X11NotifySource(ClipSource):
    """clipnotify with no flags supports old releases and monitors both buffers.

    Only the configured selections are read on notification. Persistent history
    in the consumer suppresses ownership re-assertions and selection overlap.
    """

    def __init__(self, tool=None, **kwargs):
        super().__init__(**kwargs)
        self.tool = tool or next(
            (tool for tool in ("xclip", "xsel") if shutil.which(tool)), None
        )
        if self.tool is None:
            raise ValueError("X11 notification requires xclip or xsel")

    def _start(self):
        self._thread(self._watch)

    def _watch(self):
        while not self._stopped.is_set():
            process = None
            try:
                process = self._spawn(["clipnotify"], stdout=subprocess.DEVNULL)
                if process is None:
                    return
                code = process.wait()
                self._release(process)
                process = None
                if self._stopped.is_set():
                    return
                if code != 0:
                    self._fallback(f"clipnotify exited with status {code}", self.tool)
                    return
                for selection in _selections(self.selection):
                    self._emit(self._read(self.tool, selection))
            except OSError as exc:
                self._fallback(str(exc), self.tool)
                return
            finally:
                self._release(process)


def select_source(cfg=None) -> ClipSource:
    """Choose a validated backend and log any missing-tool fallback."""
    if cfg is None:
        cfg = readConfig()
    settings = getClipboardSettings(cfg)
    backend = settings.backend
    reader = _reader_tool()
    wayland_session = bool(os.environ.get("WAYLAND_DISPLAY"))
    wayland = bool(wayland_session and shutil.which("wl-paste"))
    if wayland and backend in {"auto", "wayland"}:
        wayland, reason = wayland_watch_support()
        if not wayland:
            log.warning(f"Wayland clipboard watching unsupported: {reason}")
    x11 = bool(
        os.environ.get("DISPLAY")
        and shutil.which("clipnotify")
        and (shutil.which("xclip") or shutil.which("xsel"))
    )
    gnome_history = _gnome_history_available(cfg)
    fallback = "gnome" if gnome_history or reader is None else "poll"
    if backend == "auto":
        if wayland:
            backend = "wayland"
        elif wayland_session:
            # XWayland clipnotify misses native Wayland copies; prefer the GNOME
            # extension's complete history over lossy live polling.
            backend = fallback
        else:
            backend = "x11" if x11 else "poll" if reader else "gnome"
    elif (backend == "wayland" and not wayland) or (backend == "x11" and not x11):
        log.warning(f"Clipboard backend {backend} unavailable; selecting fallback")
        backend = fallback
    elif backend == "poll" and reader is None:
        log.warning("Clipboard polling unavailable; selecting GNOME history")
        backend = "gnome"
    kwargs = {"selection": settings.selection, "sleeptime": settings.sleeptime}
    if backend == "gnome":
        source = GnomeHistorySource(
            sleeptime=getClipboardSleepTime(cfg, gnome=True), cfg=cfg
        )
    elif backend == "wayland":
        source = WaylandWatchSource(**kwargs)
    elif backend == "x11":
        source = X11NotifySource(**kwargs)
    else:
        source = PollSource(tool=reader, **kwargs)
    log.info(f"Clipboard backend: {backend}; selection: {settings.selection}")
    return source
