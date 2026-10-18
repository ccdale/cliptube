# cliptube

cliptube watches your clipboard history for media links, then queues downloads locally.

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

1. `cliptube` reads clipboard history from GNOME Clipboard Indicator JSON history.
2. New URLs are classified as video, playlist, or BBC programme links.
3. BBC links are written as get_iplayer PVR files when `[bbc].enabled` is true.
4. Other URLs are queued into a local worker, which runs:
	- `yt-dlp` for video URLs
	- `yt-dlp -o /mnt/nas/youtube/playlists/%(playlist_title)s/%(title)s.%(ext)s` for playlists
5. If cliptube is interrupted, pending download tasks are saved to `~/.cache/cliptube/pending_queue.json` and restored on next startup.

## Requirements

- Python 3.11+
- `uv` (for dependency and run workflow)
- A working `yt-dlp` binary
- Access to the standalone iPlayer module repository at `../iplayer` when developing from source
- For clipboard watching: GNOME Clipboard Indicator history file at the configured path

## Install For Development

From this repository root:

```bash
uv sync
```

This project uses a local source dependency for iPlayer:

```toml
[tool.uv.sources]
iplayer = { path = "../iplayer" }
```

So the sibling repository is expected at:

```text
/home/chris/src/iplayer
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

Set `[bbc] enabled = false` to keep detecting BBC URLs without generating PVR files. These URLs will still be recorded in Cliptube's history as seen.

BBC programme URLs are recognized by their hostname and `/iplayer/` or `/sounds/` path. PVR generation supports the documented episode and series routes; an unrecognized route is logged instead of being passed to yt-dlp.

## Run Commands

Installed entry points:

- `cliptube` - clipboard watcher and local queue processor

Run directly with uv:

```bash
uv run cliptube
```

BBC PVR files are written to `[bbc].pvrdir` (the default is `/mnt/nas/docker/get_iplayer/config/.get_iplayer/pvr`) and assigned to UID/GID `1000`.

## Systemd User Services

Helper scripts are included:

- `scripts/install-cliptube.sh`

These scripts:

- copy service files to `~/.config/systemd/user`
- enable the relevant user service
- start the service immediately

Service templates are in:

- `configs/cliptube.service`

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
