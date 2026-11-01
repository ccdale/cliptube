# cliptube

cliptube watches clipboard changes for media links, then queues downloads locally.

Legacy/removed workflow reference (pre-cleanup snapshot):

- https://github.com/ccdale/cliptube/tree/3d21d05da03d79f84a2bfb7ce99ba8d3698ac8a5

Current support:

- YouTube videos
- YouTube playlists
- BBC iPlayer TV and BBC Sounds radio episode/series links (written as get_iplayer PVR files)

The project includes:

- A clipboard watcher service (`cliptube`) that discovers new URLs.
- A local queue worker that processes downloads sequentially and can recover pending work after restart.

## How It Works

1. `cliptube` reads GNOME Clipboard Indicator history (the default), or watches the live X11/Wayland clipboard.
2. New URLs are classified as video, playlist, or BBC programme links.
3. BBC links are queued to write get_iplayer PVR files when `[bbc].enabled` is true.
4. Other URLs are queued into a local worker, which runs:
	- `yt-dlp` for video URLs
	- `yt-dlp -o /mnt/nas/youtube/playlists/%(playlist_title)s/%(title)s.%(ext)s` for playlists
5. Every accepted URL is recorded in `~/.config/cliptube.history` before processing.
   Pending and interrupted tasks are restored on next startup; completed and failed tasks are not repeated.

## Requirements

- Python 3.11+
- `uv` (for dependency and run workflow)
- A working `yt-dlp` binary
- For GNOME history: Clipboard Indicator history file at the configured path
- For X11/XFCE event watching: `clipnotify` and `xclip` (or `xsel`)
- For Wayland event watching: `wl-clipboard` (`wl-paste`); the compositor must support its watch protocol

## Install For Development

From this repository root:

```bash
uv sync
```

## Configuration

cliptube reads config from:

```text
~/.config/cliptube.cfg
```

If this file does not exist, runtime will fail with a config-not-found error.

A sample config is provided in `configs/cliptube.cfg`.

Important keys:

- `[mediaserver].ytdlpbin`: path to `yt-dlp` binary
- `[gnomeclipindicator].histfile`: clipboard history JSON file to read
- `[gnomeclipindicator].sleeptime`: poll interval for clipboard checks
- `[bbc].enabled`: whether BBC iPlayer and BBC Sounds URLs generate PVR files (`true` by default)
- `[bbc].pvrdir`: directory for generated get_iplayer PVR files; defaults to `/mnt/nas/docker/get_iplayer/config/.get_iplayer/pvr`

### Clipboard sources

Existing installations continue using GNOME history. To try the new desktop backends:

```ini
[clipboard]
backend = auto
selection = clipboard
sleeptime = 1
historydays = 365
```

- `backend`: `gnome` (default), `auto`, `wayland`, `x11`, or `poll`.
  `auto` prefers Wayland with `wl-paste --watch`, then X11 with `clipnotify` and a reader,
  then live polling, then GNOME history. The selected backend is logged.
  Wayland watching needs the compositor's data-control protocol (KDE, Sway, Hyprland);
  GNOME/Mutter lacks it. `auto` probes for it at startup. In a Wayland session
  without it, `auto` uses GNOME Clipboard Indicator history when its file exists,
  otherwise live polling; XWayland `clipnotify` is not used there because it misses
  native Wayland copies.
- `selection`: `clipboard` (default), `primary` (select-to-copy), or `both`.
  GNOME history cannot distinguish selections and ignores this setting.
- `sleeptime`: positive interval in seconds, used only for live polling.
  GNOME retains `[gnomeclipindicator].sleeptime`.
- `historydays`: positive number of days to retain completed URLs (default `365`).
  Pending, running and failed entries are never pruned.

Event sources block while idle instead of polling the clock. Live polling uses
an interruptible event wait, not a busy loop. If an event watcher exits unexpectedly,
Cliptube logs the failure and switches to live polling. Clipboard text is read once
at startup; changes made while the service is stopped cannot otherwise be recovered.
Rapidly overwritten clipboard contents can still be missed by the compositor or
X11 reader; these backends do not promise a complete clipboard history.

### Durable history and recovery

`~/.config/cliptube.history` contains one JSON object per line, with URL, task type,
timestamps and `state`: `queued`, `running`, `done`, or `failed`.
All sources and selections share this ledger, suppressing clipboard re-assertions
and repeated copies. Writes are atomic and synchronized between workers.

- Success is recorded only after yt-dlp exits successfully, or a BBC PVR is written.
- BBC handling disabled by config records `done` with `outcome = disabled`,
  meaning deliberately skipped, not downloaded.
- `queued` and `running` records are retried on startup, including after a crash.
  Interrupted downloads retain their `running` state; yt-dlp can resume partial files.
- Failed tasks are logged at ERROR with their URL and exit code where available.
  They are not retried automatically or by re-copying. Stop Cliptube before manually
  removing a failed record to retry it.
- The old `cliptube.list` is imported as completed history and left untouched.
  Pending tasks in `pending_queue.json` take precedence over the old seen list
  during initial migration. That cache is removed only after the new ledger is persisted.
  Corrupt history aborts startup rather than discarding work.

Set `[bbc] enabled = false` to keep detecting BBC URLs without generating PVR files. These URLs will still be recorded in Cliptube's history as seen.

BBC programme URLs are recognized by their hostname and `/iplayer/` or `/sounds/` path. PVR generation supports the documented episode and series routes; an unrecognized route is logged instead of being passed to yt-dlp.

## Run Commands

Installed entry points:

- `cliptube` - clipboard watcher and local queue processor

Run directly with uv:

```bash
uv run cliptube
```

BBC PVR files are written to `[bbc].pvrdir` (the default is `/mnt/nas/docker/get_iplayer/config/.get_iplayer/pvr`). Ownership is assigned by the mounted filesystem; confirm the get_iplayer container can read files with that ownership.

## Systemd User Services

Helper scripts are included:

- `scripts/install-cliptube.sh`

These scripts:

- copy service files to `~/.config/systemd/user`
- enable the relevant user service
- start the service immediately

Service templates are in:

- `configs/cliptube.service`

On SIGTERM/SIGINT, Cliptube stops accepting work, sends SIGTERM to each download's
dedicated process group, then SIGKILL after a two-second grace period if necessary.
This includes yt-dlp's ffmpeg children even if the yt-dlp process has already exited.
It does not wait for the queue to drain, and unfinished tasks are already durable.

The template uses `TimeoutStopSec=10` and `KillMode=control-group` as a backstop.
For an existing user unit, add these under `[Service]`, then run:

```bash
systemctl --user daemon-reload
systemctl --user restart cliptube.service
```

Cliptube does not modify your installed systemd unit. X11/Wayland sources also need
the session's `DISPLAY`/`WAYLAND_DISPLAY`, `XAUTHORITY` where applicable, and
`XDG_RUNTIME_DIR` in the user service environment. Import these from your desktop
session if your login setup does not already provide them.

## URL Detection Rules (Current)

The clipboard scanner currently accepts:

- `youtube.com/watch?...`
- `youtu.be/...`
- `youtube.com/shorts/...`
- `youtube.com/playlist?...`
- `bbc.co.uk/iplayer/episodes/...` and `bbc.co.uk/iplayer/episode/...`
- `bbc.co.uk/sounds/brand/...` and `bbc.co.uk/sounds/play/...`

## Testing And Linting

```bash
uv run ruff check .
uv run pytest
```

## Notes

- Playlist output path is currently hard-coded in the queue worker.
- `cliptube` enforces a single running instance using `/tmp/cliptube.pid`.
