import json
import os
import re
import sys
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ccalogging

from cliptube import errorNotify
from cliptube.config import expandPath, readConfig
from cliptube.pvr import is_bbc_programme_url, parse_bbc_url

log = ccalogging.log


def checkUrl(txt):
    if txt is None:
        return None
    parsed = urlparse(txt.strip())
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path == "/watch":
        log.debug(f"detected youtube url '{txt}'")
        dparsed = parse_qs(parsed.query)
        log.debug(f"{dparsed=}")
        if "v" in dparsed:
            vid = dparsed["v"][0]
            log.debug(f"video {vid} extracted from url")
            return f"https://www.youtube.com/watch?v={vid}"
    if (
        host == "youtu.be"
        or (
            host in {"youtube.com", "www.youtube.com", "m.youtube.com"}
            and (parsed.path.startswith("/shorts/") or parsed.path == "/playlist")
        )
    ):
        return txt.strip()
    try:
        parse_bbc_url(txt)
    except ValueError:
        if not is_bbc_programme_url(txt):
            return None
    return txt.strip()


def extract_urls(text):
    """Extract supported, normalized URLs from arbitrary clipboard text."""
    urls = []
    for candidate in re.findall(r"https?://[^\s<>\"']+", text):
        url = checkUrl(candidate)
        if url and url not in urls:
            urls.append(url)
    return urls


def task_type(url):
    if is_bbc_programme_url(url):
        return "b"
    return "p" if "playlist" in url else "v"


class HistoryStore:
    """Single-process durable ledger shared by clipboard sources and workers."""

    def __init__(self, path=None, historydays=365, legacy_list=None, legacy_cache=None):
        self.path = Path(path or expandPath("~/.config/cliptube.history"))
        self.lock = threading.RLock()
        self.records = {}
        old_list = Path(legacy_list or expandPath("~/.config/cliptube.list"))
        old_cache = Path(legacy_cache or expandPath("~/.cache/cliptube/pending_queue.json"))
        existing = self.path.exists()
        if existing:
            with self.path.open() as stream:
                for line_number, line in enumerate(stream, 1):
                    try:
                        record = json.loads(line)
                        self._validate(record)
                    except (ValueError, TypeError, KeyError) as exc:
                        raise ValueError(
                            f"Invalid history record at {self.path}:{line_number}: {exc}"
                        ) from exc
                    self.records[record["url"]] = record
        elif old_list.exists():
            for line in old_list.read_text().splitlines():
                url = checkUrl(line)
                if url:
                    self.records[url] = self._record(url, task_type(url), "done")
        # Pending work takes precedence over the old snapshot's "seen" entries.
        if old_cache.exists():
            cached = json.loads(old_cache.read_text())
            if not isinstance(cached, list):
                raise ValueError(f"Invalid pending queue: {old_cache}")
            for task in cached:
                url = task["url"]
                record = self.records.get(url)
                if record is None or (not existing and record["state"] == "done"):
                    self.records[url] = self._record(url, task_type(url), "queued")
        cutoff = datetime.now(UTC) - timedelta(days=historydays)
        self.records = {
            url: record for url, record in self.records.items()
            if record["state"] != "done"
            or datetime.fromisoformat(record["updated"]) >= cutoff
        }
        self._write(self.records)
        if old_cache.exists():
            old_cache.unlink()

    @staticmethod
    def _validate(record):
        if not isinstance(record["url"], str) or not record["url"]:
            raise ValueError("URL must be a non-empty string")
        if record["state"] not in {"queued", "running", "done", "failed"}:
            raise ValueError("Unknown history state")
        if record.get("vtype", task_type(record["url"])) not in {"v", "p", "b"}:
            raise ValueError("Unknown task type")
        for field in ("seen", "updated"):
            if datetime.fromisoformat(record[field]).tzinfo is None:
                raise ValueError("History timestamps must include a timezone")

    @staticmethod
    def _record(url, vtype, state):
        now = datetime.now(UTC).isoformat()
        return {"url": url, "vtype": vtype, "state": state, "seen": now, "updated": now}

    def _write(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, delete=False
            ) as stream:
                temporary = stream.name
                for record in records.values():
                    stream.write(json.dumps(record) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary is not None:
                os.unlink(temporary)

    def accept(self, url, vtype=None):
        with self.lock:
            if url in self.records:
                return False
            records = dict(self.records)
            records[url] = self._record(url, vtype or task_type(url), "queued")
            self._write(records)
            self.records = records
            return True

    def transition(self, url, state, **details):
        if state not in {"running", "done", "failed"}:
            raise ValueError(f"Invalid transition state: {state}")
        with self.lock:
            records = dict(self.records)
            records[url] = {
                **records[url], **details, "state": state,
                "updated": datetime.now(UTC).isoformat(),
            }
            self._write(records)
            self.records = records

    def pending(self):
        with self.lock:
            pending = [
                dict(record) for record in self.records.values()
                if record["state"] in {"queued", "running"}
            ]
            return sorted(pending, key=lambda record: record["state"] != "running")


def readGnomeClipIndicatorFile(cfg=None):
    try:
        cfg = readConfig() if cfg is None else cfg
        histfile = expandPath(cfg["gnomeclipindicator"]["histfile"])
        with open(histfile, "r") as ifn:
            hist = json.load(ifn)
        return list(dict.fromkeys(
            url for entry in hist for url in extract_urls(entry["contents"])
        ))
    except (json.JSONDecodeError, KeyError, OSError, TypeError) as e:
        errorNotify(sys.exc_info()[2], e)
        return []
