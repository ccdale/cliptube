# TODO: event-driven clipboard watching

Replace history-file polling with a blocking clipboard watcher, so the idle process
makes zero wake-ups and never misses a copy. Polling stays as the fallback.

## Goals

- Zero CPU while idle: block in the kernel until the clipboard changes.
- No missed copies (a URL replaced within one poll interval is currently lost).
- Works on GNOME, XFCE and Wayland compositors without a backend per desktop.
- Clean, fast shutdown on SIGTERM (systemd), with no orphaned watcher child.
- Existing GNOME `clipboard-indicator` polling remains the default until the new
  backend is verified on the new laptop.

## Backends

| Backend    | Session | Tool                       | Mechanism                                  |
|------------|---------|----------------------------|--------------------------------------------|
| `gnome`    | any     | (existing history file)    | poll `[gnomeclipindicator] histfile`       |
| `wayland`  | Wayland | `wl-paste` (wl-clipboard)  | `wl-paste --watch <cmd>` runs on each change |
| `x11`      | X11     | `clipnotify` + `xclip`/`xsel` | `clipnotify` blocks until a change, then read |
| `poll`     | any     | `wl-paste`/`xclip`/`xsel`  | read live clipboard every `sleeptime`      |

`auto` selects: Wayland (`WAYLAND_DISPLAY` set and `wl-paste` found) -> X11
(`DISPLAY` set and `clipnotify` found) -> `poll` if a reader tool exists ->
`gnome`. The chosen backend is logged at startup.

## Config

```ini
[clipboard]
backend = gnome        ; gnome | auto | wayland | x11 | poll
selection = clipboard  ; clipboard | primary | both
sleeptime = 1          ; poll backend only
```

Default stays `gnome`, so existing installs are unchanged. `[gnomeclipindicator]`
keeps its current keys.

`selection` is a tertiary option, defaulting to `clipboard`. `primary` is the
select-to-copy buffer; `both` watches each and funnels them into the same queue.
It is ignored by the `gnome` backend, which only has the extension's history.
Wayland uses `wl-paste --primary`; X11 uses `clipnotify -s primary` and
`xclip -selection primary`.

## History file (cumulative, with completion state)

Today `~/.config/cliptube.list` is only a snapshot of the GNOME history, rewritten on
every poll, so it can neither suppress re-assertions nor record progress. Replace
it with a cumulative history that every backend shares.

### Format

One JSON object per line (JSONL) in `~/.config/cliptube.history`:

```json
{"url": "https://www.youtube.com/watch?v=abc", "state": "done", "seen": "2026-10-28T14:39:58Z", "updated": "2026-10-28T14:41:10Z"}
```

States and transitions:

- `queued`: accepted and put on the work queue (written before the worker runs).
- `running`: a worker has started the download (set as the task is picked up).
- `done`: the download completed successfully (exit code 0). For BBC URLs this is
  the point where the PVR file was written.
- `failed`: the command exited non-zero or the PVR write failed.

### Behaviour

- **De-duplication:** a URL already in the history in any state is ignored when it
  appears again, whichever selection or backend it came from. This handles
  Clipman's re-assertions and the `primary`/`both` overlap.
- **Resume after shutdown:** on startup, every `queued` or `running` entry is
  re-queued ahead of new work. A `running` entry means a shutdown killed it
  part-way, so it is restarted from scratch (yt-dlp resumes partial files itself).
  This makes the history the source of truth, so `pending_queue.json` is retired
  once the migration below is done.
- **Failures (decided):** `failed` entries are never retried automatically, and
  copying the URL again does not retry it. Each failure is logged at ERROR (URL
  and exit code). They stay in the history; clear one by hand to retry.
- **Crashes (decided):** `running` entries are always retried on start, whether
  the previous stop was clean or a crash.
- **Writes:** one writer, guarded by a lock because workers update state from
  threads. Rewrite via a temp file in the same directory and `os.replace` so a
  kill mid-write cannot truncate the history.
- **Size:** keep `done` entries for a configurable number of days
  (`[clipboard] historydays`, default 365), pruned at startup. Never prune
  `queued`, `running` or `failed`.
- **Migration:** if the old `cliptube.list` exists and the new file does not,
  import each line as `done` (they were already handled), then leave the old
  file in place untouched.

## Design

### Module layout

- New `src/cliptube/clipsource.py` holding a small interface:
  - `class ClipSource` with `start()`, `stop()` and `wait_for_change(timeout) -> str | None`.
  - Implementations: `GnomeHistorySource`, `WaylandWatchSource`, `X11NotifySource`, `PollSource`.
  - `select_source(cfg) -> ClipSource` implementing `auto` and the fallbacks.
- `wclipboard.watchGnomeClipboard` is renamed `watchClipboard` (the `cliptube`
  script entry in `pyproject.toml` is updated to match) and loops on the source
  instead of `ev.wait(sleeptime)`.
- `history.getNewUrls` is split so the URL-extraction and "already seen" logic
  works on a plain string as well as on the GNOME history list. Recording seen
  URLs is unchanged.

### Wayland (`wl-paste --watch`)

- Spawn `wl-paste --type text --watch <helper>` with `Popen`, `stdout=PIPE`.
- `<helper>` is `cat`, so each clipboard change writes the new text to stdout.
  Multi-line content is length-framed using `--watch sh -c 'printf "%s\0" "$(cat)"'`
  (NUL-delimited records) to avoid splitting on newlines.
- A reader thread blocks on `stdout` and pushes each record onto a
  `queue.Queue`. `wait_for_change` is `queue.get(timeout=...)`, which is a kernel
  wait and gives no idle CPU use.
- If the child exits unexpectedly, log it and fall back to `poll` after a short
  back-off (do not busy-restart).

### X11 (`clipnotify`)

- Loop: run `clipnotify -s clipboard` (blocks until the selection owner changes),
  then read with `xclip -o -selection clipboard` (or `xsel -bo`), push to the queue.
- Run in a worker thread, with the `clipnotify` child tracked so shutdown can kill it.
- Note that XFCE's Clipman keeps ownership of the clipboard, so `clipnotify` fires
  on its re-assertions too; these are dropped by the history-file de-duplication above.

### Poll fallback

- Read the live clipboard on each `ev.wait(sleeptime)` timeout, as today. No new
  sleeping mechanism is needed (`Event.wait` already blocks in the kernel).

### Shutdown and signals

- Keep `interruptWP` setting `ev`. Add `source.stop()` to it: terminate the
  child (`terminate`, 2s wait, then `kill`), mirroring `LocalQueueProcessor.interrupt`.
- Start the child with `start_new_session=True` and kill its process group so
  helper processes cannot be orphaned.
- The main loop uses `source.wait_for_change`, which `stop()` unblocks by pushing a
  sentinel onto the queue, so shutdown stays prompt.

### Fast shutdown (target: a few seconds, never 90)

Cause of the 90s stop: `interruptWP` forces a shutdown, but after the loop exits
`watchClipboard` calls `processor.shutdown(timeout=90, wait_for_current=True,
force=False)`, which waits for the running yt-dlp to finish. Remove that wait.

- Every download child (yt-dlp and its ffmpeg helpers) is started with
  `start_new_session=True`, so it leads its own process group.
- Stop sequence, one place only (`LocalQueueProcessor.interrupt_all`):
  1. `os.killpg(pgid, SIGTERM)` for each running download group.
  2. Wait up to 2s (`Popen.wait(timeout)`) for the groups to exit.
  3. `os.killpg(pgid, SIGKILL)` for any survivors.
  4. Tolerate `ProcessLookupError` (group already gone).
- Interrupted tasks stay `running` in the history (not `failed`), so the next
  start re-queues them. Partial files are left for yt-dlp to resume.
- Workers must not pick up another task once shutdown starts (check the stop
  flag before dequeue), so nothing new is started after SIGTERM.
- The final "check for urls before shutting down" runs only as a quick history
  read; it must not wait on any download.
- Systemd backstop: set `TimeoutStopSec=10` in `cliptube.service`. systemd
  already SIGKILLs the whole cgroup after that, so a stuck stop cannot take 90s.
  Document this in the README; the unit lives outside the repo.
- Failures are logged at ERROR with the URL and exit code when a task is marked
  `failed`; interrupted tasks are logged at INFO as "interrupted, will retry".

### Behaviour preserved

- Single-instance pid file, BBC `[bbc] enabled` switch, URL sorting and
  queue ordering are untouched.
- A copy made while the service is down is not seen by the event backends. On
  start, read the current clipboard once so the latest value is processed (the
  history file stops it being processed twice).

## Tasks

- [ ] Extract URL parsing in `history.py` so it accepts a string, with tests.
- [ ] Implement the cumulative JSONL history (atomic writes, lock, pruning) with
      `queued`/`running`/`done`/`failed` states, and tests for each transition.
- [ ] Migrate `cliptube.list` entries as `done`.
- [ ] Have the queue workers set `running` on pickup and `done`/`failed` on exit
      (including the BBC PVR path); re-queue `queued`/`running` entries on startup;
      then drop `pending_queue.json`.
- [ ] Add `clipsource.py` with the `ClipSource` interface and `PollSource`.
- [ ] Add `[clipboard]` config reading with defaults and validation (unknown
      `backend` or `selection` gives a clear error), including sample config and README docs.
- [ ] Support `selection = clipboard | primary | both` in the Wayland, X11 and poll sources.
- [ ] Implement `WaylandWatchSource` with NUL framing, reader thread and unexpected-exit fallback.
- [ ] Implement `X11NotifySource` with de-duplication.
- [ ] Implement `select_source` (`auto` order, missing-tool fallback, startup log line).
- [ ] Rewire `wclipboard` to the source loop, rename the entry point, and keep `uv run cliptube` working.
- [ ] Hook `source.stop()` into the SIGTERM handler; verify no child survives.
- [ ] Fast shutdown: start downloads in their own session, SIGTERM then SIGKILL
      the process group (2s grace), remove the 90s `wait_for_current` shutdown,
      stop workers taking new tasks, keep interrupted tasks `running`.
- [ ] Test shutdown with a fake long-running child that ignores SIGTERM: the
      group is killed within the grace period and the task stays `running`.
- [ ] Manual check: `systemctl --user stop cliptube` during a real yt-dlp
      download returns in under ~5s and leaves no yt-dlp/ffmpeg processes.
- [ ] Unit tests with a fake child process (no real clipboard): framing, de-dup,
      child exit, stop unblocks `wait_for_change`, `auto` selection.
- [ ] Manual verification: GNOME (unchanged default), then XFCE on the new laptop
      (`clipnotify` + Clipman) and `systemctl --user stop cliptube` returns quickly.

## Open questions

- Packages to document: `wl-clipboard`, `clipnotify`, `xclip` (or `xsel`).
