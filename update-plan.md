# Cliptube Update TODO

## 1. Make BBC response configurable

- [x] Add a configuration option that enables or disables Cliptube's response to BBC iPlayer and BBC Sounds URLs.
- [x] When the option is disabled, leave BBC URLs unqueued; keep current YouTube handling unchanged.
- [x] Document the option, its default, and how to change it.
- [x] Add tests for both enabled and disabled behavior.

## 2. Generate get_iplayer PVR files

- [x] Replace the current BBC download response with generation of `get_iplayer` PVR files.
- [x] Use the parser in `pvr-maker.tmp.py` as a starting point; move the reusable function into Cliptube and remove the hardcoded test URLs and top-level test execution.
- [x] Extract the programme identifier/search string, media type (`tv` or `radio`), and whether the URL represents a series or episode.
- [x] Parse URL path segments without assuming a fixed PID length, while retaining explicit supported BBC route modes.
- [x] Generate recursive PVR entries for series and single-programme entries for episodes, following the examples below.
- [x] Keep the search string free of labels such as `Series 3`; the correct search string lets get_iplayer's history record episodes without excluding them by series number.
- [x] Add tests for all four example URL types, generated PVR contents, unsupported URLs, and search strings without `Series #` labels.
- [x] Write generated files directly to the configured `[bbc].pvrdir`, defaulting to `/mnt/nas/docker/get_iplayer/config/.get_iplayer/pvr`.
- [x] Keep that default in code while allowing `[bbc].pvrdir` in `~/.config/cliptube.cfg` to override it.
- [ ] Verify get_iplayer can read files with mount-assigned ownership (currently observed as UID 1000, GID 10); do not call `os.chown()` from Cliptube.

The temporary `pvr-maker.tmp.py` prototype and its hardcoded import-time test run have been removed after integration.

## 3. Run PVR jobs in get_iplayer

- [ ] Confirm the existing scheduled PVR run picks up files written directly to the mounted PVR directory without a separate trigger.
- [ ] Verify the container can read PVR files with the NAS mount's assigned ownership.
- [ ] No `incoming` directory, container-side watcher, or Compose change is needed for PVR-file import.

Invalid PVR files are intentionally handled manually: get_iplayer logs them, and the operator monitors the logs and removes or adjusts invalid files. Do not add automated validation or repair.

## 4. Organize completed downloads on the NAS

- [ ] Add a post-download process that moves completed files from the download location to their permanent NAS locations.
- [ ] Identify whether each download is TV or radio before choosing its destination.
- [ ] For TV, use `/druidshare/Video/Drama/<title> (<year>)/` and create missing series directories.
- [ ] For radio, use `/druidshare/AudioBooks/Radio/<title>/` and create missing programme directories.
- [ ] Investigate theTVDB as a possible source of TV series and episode metadata; do not depend on it for radio metadata.
- [ ] Identify a suitable source for BBC radio programme titles and metadata.
- [ ] Define how titles and years are obtained, and how existing files or name collisions are handled.
- [ ] Test TV and radio placement, directory creation, and failure/retry behavior.

## Decisions to settle

- [ ] Decide how failed post-download moves are reported and retried.
- [ ] Confirm the title/year metadata source and the exact TV directory naming convention.

## Current Docker Compose Setup

Reference configuration. PVR files will be written to the host-mounted NAS path directly; no `incoming` volume or container watcher is planned.

```yaml
# version: "3.8"
services:
  get_iplayer:
    image: ghcr.io/thespad/get_iplayer:latest
    container_name: get_iplayer
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London
      - INCLUDERADIO=true
    volumes:
      - /home/chris/druidshare/docker/get_iplayer/config:/config
      - /home/chris/druidshare/iplayer:/downloads
    ports:
      - "1935:1935"
    restart: unless-stopped
# This keeps WebPVR running in the background while performing the PVR check every 12 hours
    entrypoint: >
      sh -c "
      (
        echo 'Waiting 60 seconds for container initialization to settle...'
        sleep 60
        while true; do
          if [ -f /app/get_iplayer/get_iplayer ]; then
            echo '=== Starting Automated Background PVR Run ==='
            su abc -s /bin/sh -c 'perl /app/get_iplayer/get_iplayer --pvr'
          fi
          sleep 43200
        done
      ) &
      exec /init"
```

## Example URLs and PVR expectations

### television series
```
https://www.bbc.co.uk/iplayer/episodes/p09fs2qh/time?seriesId=p09fs2qh-structural-3-m00316gj
```
The pvr file for this series would be
```
pid p09fs2qh
pidrecursive 1
type tv
```
Use the programme search string without a `Series #` label so get_iplayer can record all matching episodes.

### television episode
```
https://www.bbc.co.uk/iplayer/episode/m00316gl/time-series-3-episode-1
```

### radio series
```
https://www.bbc.co.uk/sounds/brand/m0024fk6
```

### radio episode
```
https://www.bbc.co.uk/sounds/play/m0030x8z
```