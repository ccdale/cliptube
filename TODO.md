# TODO: event-driven clipboard watching

Replace history-file polling with a blocking clipboard watcher, so the idle process
makes no timed idle wake-ups. Polling stays as the fallback.

## Goals

- Zero CPU while idle: block in the kernel until the clipboard changes.
- Reduce missed copies compared with periodic polling. Clipboard protocols and
  delayed X11 reads can still miss rapidly overwritten contents.
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
Wayland uses `wl-paste --primary`. X11 uses flagless `clipnotify` (compatible
with older releases) and reads the requested selection with
`xclip -selection primary` or `clipboard`.

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
  BBC handling disabled by configuration is explicitly recorded as `done` with
  `outcome = disabled` (deliberately skipped, not downloaded).
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
  - `class ClipSource` with `start()`, `stop()`, a signal-safe `wake()`, and
    `wait_for_change(timeout) -> str | None`.
  - Implementations: `GnomeHistorySource`, `WaylandWatchSource`, `X11NotifySource`, `PollSource`.
  - `select_source(cfg) -> ClipSource` implementing `auto` and the fallbacks.
- `wclipboard.watchGnomeClipboard` is renamed `watchClipboard` (the `cliptube`
  script entry in `pyproject.toml` is updated to match) and loops on the source
  instead of `ev.wait(sleeptime)`.
- `history.getNewUrls` is split so the URL-extraction and "already seen" logic
  works on a plain string as well as on the GNOME history list. Recording seen
  URLs moves to the cumulative ledger.

### Wayland (`wl-paste --watch`)

- Spawn `wl-paste --type text --watch <helper>` with `Popen`, `stdout=PIPE`.
- Use a Python helper to forward length-prefixed clipboard records.
  Avoid shell command substitution, which changes trailing newlines.
- A reader thread blocks on `stdout` and pushes each record onto a
  `queue.SimpleQueue`. The main loop uses `wait_for_change(None)`, which is a kernel
  wait and gives no idle CPU use.
- If the child exits unexpectedly, log it and fall back to `poll` after a short
  back-off (do not busy-restart).

### X11 (`clipnotify`)

- Loop: run `clipnotify` (blocks until a selection owner changes),
  then read with `xclip -o -selection clipboard` (or `xsel -bo`), push to the queue.
- Run in a worker thread, with the `clipnotify` child tracked so shutdown can kill it.
- Note that XFCE's Clipman keeps ownership of the clipboard, so `clipnotify` fires
  on its re-assertions too; these are dropped by the history-file de-duplication above.

### Poll fallback

- Read the live clipboard on each `ev.wait(sleeptime)` timeout, as today. No new
  sleeping mechanism is needed (`Event.wait` already blocks in the kernel).

### Shutdown and signals

- `interruptWP` only sets the stop event and wakes the source. Do not perform
  joins, history writes or process termination inside a signal handler.
- Main-loop cleanup stops downloads and the source exactly once.
- Start the child with `start_new_session=True` and kill its process group so
  helper processes cannot be orphaned.
- The main loop uses `source.wait_for_change`, which `stop()` unblocks by pushing a
  sentinel onto the queue, so shutdown stays prompt.

### Fast shutdown (target: a few seconds, never 90)

The old signal handler forced a shutdown, but the main loop then called shutdown
again. Its `Queue.join()` waited for all unfinished work, not just the current
download, and did not honor the supplied 90-second timeout. Remove that wait.

- Every download child (yt-dlp and its ffmpeg helpers) is started with
  `start_new_session=True`, so it leads its own process group.
- Stop sequence, one place only (`LocalQueueProcessor.interrupt_all`):
  1. `os.killpg(pgid, SIGTERM)` for each running download group.
  2. Wait up to 2s total for the groups to exit.
  3. `os.killpg(pgid, SIGKILL)` for any survivors.
  4. Tolerate `ProcessLookupError` (group already gone).
- Interrupted tasks stay `running` in the history (not `failed`), so the next
  start re-queues them. Partial files are left for yt-dlp to resume.
- Check group liveness even if the leader exits; ffmpeg can still be running
  and holding output pipes open.
- Workers must not pick up another task once shutdown starts (check the stop
  flag before dequeue), so nothing new is started after SIGTERM.
- Do not do a final clipboard scan after the stop event: it can accept new work
  or block on a clipboard reader during shutdown.
- Systemd backstop: set `TimeoutStopSec=10` in `cliptube.service`. systemd
  already SIGKILLs the whole cgroup after that, so a stuck stop cannot take 90s.
  Document this in the README and update the repository's template. Applying
  the change to the installed user unit remains a manual task.
- Failures are logged at ERROR with the URL and exit code when a task is marked
  `failed`; interrupted tasks are logged at INFO as "interrupted, will retry".

### Behaviour preserved

- Single-instance pid file, BBC `[bbc] enabled` switch, URL sorting and
  queue ordering are untouched.
- A copy made while the service is down is not seen by the event backends. On
  start, read the current clipboard once so the latest value is processed (the
  history file stops it being processed twice).

## Tasks

- [x] Extract URL parsing in `history.py` so it accepts a string, with tests.
- [x] Implement the cumulative JSONL history (atomic writes, lock, pruning) with
      `queued`/`running`/`done`/`failed` states, and tests for each transition.
- [x] Migrate `cliptube.list` entries as `done`.
- [x] Have the queue workers set `running` on pickup and `done`/`failed` on exit
      (including the BBC PVR path); re-queue `queued`/`running` entries on startup;
      then drop `pending_queue.json`.
- [x] Add `clipsource.py` with the `ClipSource` interface and `PollSource`.
- [x] Add `[clipboard]` config reading with defaults and validation (unknown
      `backend` or `selection` gives a clear error), including sample config and README docs.
- [x] Support `selection = clipboard | primary | both` in the Wayland, X11 and poll sources.
- [x] Implement `WaylandWatchSource` with length framing, reader thread and unexpected-exit fallback.
- [x] Implement `X11NotifySource` with de-duplication.
- [x] Implement `select_source` (`auto` order, missing-tool fallback, startup log line).
- [x] Rewire `wclipboard` to the source loop, rename the entry point, and keep `uv run cliptube` working.
- [x] Wake the source in the SIGTERM handler and stop it in main-loop cleanup;
      verify children are stopped in automated tests.
- [x] Fast shutdown: start downloads in their own session, SIGTERM then SIGKILL
      the process group (2s grace), remove the 90s `wait_for_current` shutdown,
      stop workers taking new tasks, keep interrupted tasks `running`.
- [x] Test shutdown with a real harmless long-running child that ignores SIGTERM: the
      group is killed within the grace period and the task stays `running`.
- [ ] Apply the updated systemd stop settings to the installed user unit.
- [ ] Manual check: `systemctl --user stop cliptube` during a real yt-dlp
      download returns in under ~5s and leaves no yt-dlp/ffmpeg processes.
- [x] Unit tests with a fake child process (no real clipboard): framing, de-dup,
      child exit, stop unblocks `wait_for_change`, `auto` selection.
- [ ] Manual verification: GNOME (unchanged default), then XFCE on the new laptop
      (`clipnotify` + Clipman) and `systemctl --user stop cliptube` returns quickly.

## Open questions

- Packages to document: `wl-clipboard`, `clipnotify`, `xclip` (or `xsel`).
