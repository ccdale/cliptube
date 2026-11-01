"""Clipboard tests use local Python children, never a desktop session."""

import configparser
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from cliptube import clipsource
from cliptube.clipsource import (
    ClipSource,
    GnomeHistorySource,
    PollSource,
    WaylandWatchSource,
    X11NotifySource,
    select_source,
)


def config(**options):
    cfg = configparser.ConfigParser()
    cfg.read_dict({"clipboard": options})
    return cfg


@pytest.fixture
def children(monkeypatch):
    """Replace desktop executables with real, session-isolated Python children."""
    original = subprocess.Popen
    calls = []
    scripts = {}

    def spawn(command, **kwargs):
        calls.append(command)
        if command[0] in scripts:
            key = "watch" if "--watch" in command else "read"
            script = scripts[command[0]]
            if isinstance(script, dict):
                script = script[key]
            command = [sys.executable, "-c", script]
        assert kwargs["start_new_session"] is True
        return original(command, **kwargs)

    monkeypatch.setattr(clipsource.subprocess, "Popen", spawn)
    yield scripts, calls


def test_gnome_joins_history_and_stop_unblocks():
    source = GnomeHistorySource(
        sleeptime=30, reader=lambda: ["https://example.org/a", "https://example.org/b"]
    )
    source.start()
    assert source.wait_for_change(1) == "https://example.org/a\nhttps://example.org/b"
    result = []
    waiter = threading.Thread(target=lambda: result.append(source.wait_for_change()))
    waiter.start()
    source.stop()
    waiter.join(1)
    assert result == [None]
    assert not waiter.is_alive()
    assert source.wait_for_change() is None
    source.stop()
    with pytest.raises(RuntimeError):
        source.start()


def test_wait_timeout():
    source = ClipSource()
    assert source.wait_for_change(0.01) is None
    source.stop()


def test_gnome_passes_selected_config_to_reader(monkeypatch):
    from cliptube import history

    cfg = config()
    received = []

    def reader(passed_cfg):
        received.append(passed_cfg)
        return ["https://example.org"]

    monkeypatch.setattr(history, "readGnomeClipIndicatorFile", reader)
    source = GnomeHistorySource(cfg=cfg, sleeptime=30)
    try:
        source.start()
        assert source.wait_for_change(1) == "https://example.org"
        assert received == [cfg]
    finally:
        source.stop()


def test_gnome_actual_history_reader_integration():
    # Keep scratch file operations within the project, not pytest's temp directory.
    path = Path.cwd() / f".clipboard-integration-{uuid.uuid4().hex}.json"
    cfg = config()
    cfg.read_dict({"gnomeclipindicator": {"histfile": str(path), "sleeptime": "30"}})
    entries = [
        {"contents": "Embedded https://www.youtube.com/watch?v=first&feature=share here"},
        {"contents": "Multiline:\nhttps://youtu.be/second\nhttps://www.youtube.com/watch?v=third"},
        {"contents": "Repeat https://youtu.be/second\nhttps://example.org/unsupported"},
    ]
    source = select_source(cfg)
    waiter = None
    try:
        path.write_text(json.dumps(entries), encoding="utf-8")
        source.start()
        assert source.wait_for_change(2) == (
            "https://www.youtube.com/watch?v=first\n"
            "https://youtu.be/second\n"
            "https://www.youtube.com/watch?v=third"
        )
        result = []
        waiter = threading.Thread(target=lambda: result.append(source.wait_for_change(None)))
        waiter.start()
        source.stop()
        waiter.join(1)
        assert not waiter.is_alive()
        assert result == [None]
    finally:
        source.stop()
        if waiter is not None:
            waiter.join(1)
        path.unlink(missing_ok=True)


def test_request_stop_defers_child_cleanup():
    source = ClipSource(grace=0.05)
    process = source._spawn([sys.executable, "-c", "import time; time.sleep(30)"])
    source.request_stop()
    assert source.wait_for_change() is None
    assert process.poll() is None
    source.stop()
    assert process.poll() is not None


def test_wake_is_safe_without_source_lock():
    source = ClipSource()
    result = []
    with source._lock:
        thread = threading.Thread(target=lambda: (source.wake(), result.append(True)))
        thread.start()
        thread.join(1)
        assert result == [True]
    assert source.wait_for_change() is None
    source.stop()


@pytest.mark.parametrize("request_first", [False, True])
def test_stop_serializes_with_spawn_and_only_signals_child_group(monkeypatch, request_first):
    original_popen = subprocess.Popen
    original_killpg = os.killpg
    spawning = threading.Event()
    release_spawn = threading.Event()
    stopping = threading.Event()
    signaled = []
    spawned = []
    source = ClipSource(grace=0.05)

    def delayed_spawn(*args, **kwargs):
        assert kwargs["start_new_session"] is True
        spawning.set()
        assert release_spawn.wait(2)
        return original_popen(*args, **kwargs)

    def tracked_killpg(pgid, sig):
        assert pgid != os.getpgrp()
        signaled.append(pgid)
        original_killpg(pgid, sig)

    def spawn():
        spawned.append(source._spawn([sys.executable, "-c", "import time;time.sleep(30)"]))

    def stop():
        stopping.set()
        source.stop()

    monkeypatch.setattr(clipsource.subprocess, "Popen", delayed_spawn)
    monkeypatch.setattr(os, "killpg", tracked_killpg)
    spawner = threading.Thread(target=spawn)
    stopper = threading.Thread(target=stop)
    spawner.start()
    try:
        assert spawning.wait(1)
        if request_first:
            source.request_stop()
        stopper.start()
        assert stopping.wait(1)
        release_spawn.set()
        spawner.join(2)
        stopper.join(2)
        assert not spawner.is_alive()
        assert not stopper.is_alive()
        assert spawned[0].poll() is not None
        assert signaled and set(signaled) == {spawned[0].pid}
        assert source._spawn([sys.executable, "-c", "pass"]) is None
    finally:
        release_spawn.set()
        spawner.join(2)
        if stopper.ident is not None:
            stopper.join(2)
        source.stop()


@pytest.mark.parametrize("script", [
    "raise SystemExit(2)",
    "import sys,time;sys.stderr.write('reader stalled\\n');sys.stderr.flush();time.sleep(30)",
])
def test_reader_error_logs_warning_and_returns_none_with_bounded_wait(children, monkeypatch, script):
    scripts, _ = children
    scripts["xclip"] = script
    messages = []
    monkeypatch.setattr(clipsource.log, "warning", messages.append)
    source = PollSource(tool="xclip", grace=0.05)
    started = time.monotonic()
    try:
        assert source._read("xclip", "clipboard") is None
        assert time.monotonic() - started < 3
        assert messages
        if "stalled" in script:
            assert "reader stalled" in messages[0]
        assert source.wait_for_change(0.01) is None
    finally:
        source.stop()


def test_reader_errors_warn_once_per_selection_until_recovery(children, monkeypatch):
    scripts, _ = children
    warnings = []
    debug = []
    monkeypatch.setattr(clipsource.log, "warning", warnings.append)
    monkeypatch.setattr(clipsource.log, "debug", debug.append)
    scripts["xclip"] = "import sys;sys.stderr.write('Cannot open display :9');sys.exit(1)"
    source = PollSource(tool="xclip", grace=0.05)
    try:
        for selection in ("clipboard", "clipboard", "primary", "primary"):
            assert source._read("xclip", selection) is None
            assert not source._processes
        assert len(warnings) == 2
        assert all("Cannot open display :9" in message for message in warnings)
        assert len(debug) == 2
        scripts["xclip"] = "print('recovered',end='')"
        assert source._read("xclip", "clipboard") == "recovered"
        scripts["xclip"] = "import sys;sys.stderr.write('Cannot open display :9');sys.exit(1)"
        assert source._read("xclip", "clipboard") is None
        assert len(warnings) == 3
    finally:
        source.stop()


@pytest.mark.parametrize("diagnostic", [
    "No selection", "No suitable type of content copied",
    "Error: target STRING not available",
])
def test_normal_empty_or_nontext_selection_logs_only_debug(children, monkeypatch, diagnostic):
    scripts, _ = children
    scripts["xclip"] = f"import sys;sys.stderr.write({diagnostic!r});sys.exit(1)"
    warnings = []
    debug = []
    monkeypatch.setattr(clipsource.log, "warning", warnings.append)
    monkeypatch.setattr(clipsource.log, "debug", debug.append)
    source = PollSource(tool="xclip", grace=0.05)
    try:
        assert source._read("xclip", "clipboard") is None
        assert warnings == []
        assert diagnostic in debug[0]
        assert not source._processes
    finally:
        source.stop()


def test_spawn_oserror_warns_once_and_retains_diagnostic(monkeypatch):
    source = PollSource(tool="xclip")
    warnings = []
    monkeypatch.setattr(clipsource.log, "warning", warnings.append)

    def missing(*args, **kwargs):
        raise FileNotFoundError("xclip executable vanished")

    monkeypatch.setattr(clipsource.subprocess, "Popen", missing)
    try:
        assert source._read("xclip", "clipboard") is None
        assert source._read("xclip", "clipboard") is None
        assert len(warnings) == 1
        assert "xclip executable vanished" in warnings[0]
        assert not source._processes
    finally:
        source.stop()


def test_short_lived_read_registry_does_not_grow(children):
    scripts, _ = children
    scripts["xclip"] = "print('text',end='')"
    source = PollSource(tool="xclip", grace=0.05)
    try:
        for _ in range(12):
            assert source._read("xclip", "clipboard") == "text"
            assert not source._processes
    finally:
        source.stop()


@pytest.mark.parametrize("selection", ["clipboard", "primary", "both"])
@pytest.mark.parametrize("tool", ["wl-paste", "xclip", "xsel"])
def test_poll_reads_selected_buffers(children, tool, selection):
    scripts, calls = children
    scripts[tool] = "import sys; sys.stdout.write('a\\nb\\n')"
    source = PollSource(tool=tool, selection=selection, sleeptime=30)
    try:
        source.start()
        count = 2 if selection == "both" else 1
        assert [source.wait_for_change(2) for _ in range(count)] == ["a\nb\n"] * count
        read_calls = calls[:count]
        for selected, command in zip(clipsource._selections(selection), read_calls, strict=True):
            assert command == clipsource._read_command(tool, selected)
    finally:
        source.stop()


def test_python_callback_preserves_arbitrary_text():
    data = b" first\nsecond\n\x00last \n"
    process = subprocess.Popen(
        [sys.executable, "-c", clipsource._WATCH_HELPER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(data, timeout=2)
        assert output[:8] == len(data).to_bytes(8, "big")
        assert output[8:] == data
    finally:
        clipsource._terminate_groups([process], 0.05)


def test_wayland_frames_both_selections(children):
    scripts, calls = children
    scripts["wl-paste"] = {
        "watch": (
            "import sys,time;"
            "out=sys.stdout.buffer;"
            "data=b'first\\nsecond\\x00third \\n';"
            "out.write(len(data).to_bytes(8,'big')+data);"
            "out.write((0).to_bytes(8,'big'));out.flush();time.sleep(30)"
        ),
        "read": "raise SystemExit(1)",
    }
    source = WaylandWatchSource(selection="both", grace=0.05)
    try:
        source.start()
        results = [source.wait_for_change(2) for _ in range(4)]
        assert results.count("first\nsecond\x00third \n") == 2
        assert results.count("") == 2
        assert sum("--primary" in call for call in calls) == 1
        assert all(call[-3:] == [sys.executable, "-c", clipsource._WATCH_HELPER] for call in calls)
    finally:
        source.stop()
    assert all(not thread.is_alive() for thread in source._threads)


@pytest.mark.parametrize("failure", ["raise SystemExit(1)", "import sys;sys.stdout.write('bad')"])
def test_wayland_unexpected_exit_falls_back_without_restart(children, failure):
    scripts, calls = children
    scripts["wl-paste"] = {
        "watch": failure,
        "read": "print('fallback',end='')",
    }
    source = WaylandWatchSource(sleeptime=30, grace=0.05)
    try:
        source.start()
        assert source.wait_for_change(3) == "fallback"
        assert len([call for call in calls if "--watch" in call]) == 1
        assert source._fallback_started
    finally:
        source.stop()


def test_wayland_exit_with_helper_holding_pipe_still_falls_back(children):
    scripts, _ = children
    scripts["wl-paste"] = {
        "watch": (
            "import os,signal,time;"
            "pid=os.fork();"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN) if pid==0 else None;"
            "time.sleep(30) if pid==0 else None"
        ),
        "read": "print('fallback',end='')",
    }
    source = WaylandWatchSource(sleeptime=30, grace=0.05)
    try:
        source.start()
        assert source.wait_for_change(3) == "fallback"
    finally:
        source.stop()
    assert all(not thread.is_alive() for thread in source._threads)


def test_x11_no_flags_and_selection_filtering(children):
    scripts, calls = children
    scripts["clipnotify"] = "import time;time.sleep(0.05)"
    scripts["xsel"] = "print('primary',end='')"
    source = X11NotifySource(tool="xsel", selection="primary", grace=0.05)
    try:
        source.start()
        assert source.wait_for_change(2) == "primary"
        assert ["clipnotify"] in calls
        assert ["xsel", "--output", "--primary"] in calls
        assert not any("--clipboard" in call for call in calls)
    finally:
        source.stop()


def test_x11_failure_falls_back(children):
    scripts, calls = children
    scripts["clipnotify"] = "raise SystemExit(1)"
    scripts["xclip"] = "print('fallback',end='')"
    source = X11NotifySource(tool="xclip", sleeptime=30, grace=0.05)
    try:
        source.start()
        assert source.wait_for_change(3) == "fallback"
        assert calls.count(["clipnotify"]) == 1
    finally:
        source.stop()


def test_hung_poll_reader_is_bounded_and_stoppable(children):
    scripts, _ = children
    scripts["xclip"] = "import time;time.sleep(30)"
    source = PollSource(tool="xclip", sleeptime=30, grace=0.05)
    source.start()
    deadline = time.monotonic() + 2
    while not source._processes and time.monotonic() < deadline:
        time.sleep(0.01)
    started = time.monotonic()
    source.stop()
    assert time.monotonic() - started < 2
    assert all(not thread.is_alive() for thread in source._threads)


def test_cleanup_kills_descendant_after_leader_exit():
    source = ClipSource(grace=0.05)
    code = """
import os, signal, time
readfd, writefd = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(readfd)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.write(writefd, b"ready")
    os.close(writefd)
    print(os.getpid(), flush=True)
    time.sleep(30)
else:
    os.close(writefd)
    os.read(readfd, 5)
    os.close(readfd)
"""
    process = source._spawn([sys.executable, "-c", code])
    child_pid = int(process.stdout.readline())
    try:
        process.wait(timeout=2)
        assert os.getpgid(child_pid) == process.pid
        assert process in source._processes
        source.stop()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                with open(f"/proc/{child_pid}/stat") as handle:
                    if handle.read().split()[2] == "Z":
                        break
            except FileNotFoundError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("descendant survived source.stop()")
    finally:
        source.stop()
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.stdout.close()


@pytest.mark.parametrize(
    ("environment", "tools", "expected"),
    [
        ({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":1"}, {"wl-paste", "clipnotify", "xclip"}, WaylandWatchSource),
        ({"DISPLAY": ":1"}, {"clipnotify", "xclip"}, X11NotifySource),
        ({"DISPLAY": ":1"}, {"clipnotify"}, GnomeHistorySource),
        ({"DISPLAY": ":1"}, {"xsel"}, PollSource),
        ({}, set(), GnomeHistorySource),
    ],
)
def test_auto_selection(monkeypatch, environment, tools, expected):
    monkeypatch.setattr(clipsource.os, "environ", environment)
    monkeypatch.setattr(clipsource.shutil, "which", lambda tool: tool if tool in tools else None)
    monkeypatch.setattr(clipsource, "wayland_watch_support", lambda: (True, ""))
    assert isinstance(select_source(config(backend="auto")), expected)


@pytest.mark.parametrize(("history_exists", "expected"), [
    (True, GnomeHistorySource),
    (False, PollSource),
])
def test_auto_wayland_without_data_control(monkeypatch, tmp_path, history_exists, expected):
    """GNOME/Mutter rejects wl-paste --watch; XWayland clipnotify is not used."""
    histfile = tmp_path / "history.json"
    if history_exists:
        histfile.write_text("[]")
    cfg = config(backend="auto")
    cfg.read_dict({"gnomeclipindicator": {"histfile": str(histfile)}})
    monkeypatch.setattr(clipsource.os, "environ", {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"})
    monkeypatch.setattr(clipsource.shutil, "which", lambda tool: tool)
    monkeypatch.setattr(
        clipsource, "wayland_watch_support",
        lambda: (False, "Watch mode requires a compositor that supports the data-control protocol"),
    )
    assert isinstance(select_source(cfg), expected)


@pytest.mark.parametrize(("script", "supported"), [
    ("import time; time.sleep(30)", True),
    ("import sys; sys.stderr.write('Watch mode requires data-control'); sys.exit(1)", False),
])
def test_wayland_watch_probe(children, script, supported):
    scripts, _calls = children
    scripts["wl-paste"] = script
    result, reason = clipsource.wayland_watch_support(timeout=0.5)
    assert result is supported
    if not supported:
        assert "status 1" in reason
        assert "data-control" in reason


def test_default_legacy_gnome_and_interval(monkeypatch):
    monkeypatch.setattr(clipsource.shutil, "which", lambda tool: tool)
    cfg = config()
    cfg.read_dict({"gnomeclipindicator": {"sleeptime": "12"}})
    source = select_source(cfg)
    assert isinstance(source, GnomeHistorySource)
    assert source.sleeptime == 12
    assert source.cfg is cfg


def test_explicit_missing_watcher_falls_back(monkeypatch):
    monkeypatch.setattr(clipsource.os, "environ", {"DISPLAY": ":1"})
    monkeypatch.setattr(clipsource.shutil, "which", lambda tool: tool if tool == "xsel" else None)
    assert isinstance(select_source(config(backend="wayland")), PollSource)


def test_poll_without_tools_falls_back_to_gnome(monkeypatch):
    monkeypatch.setattr(clipsource.shutil, "which", lambda tool: None)
    assert isinstance(select_source(config(backend="poll")), GnomeHistorySource)
