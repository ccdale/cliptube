# Cliptube Update TODO

## 1. Make BBC response configurable

- [x] Add a configuration option that enables or disables Cliptube's response to BBC iPlayer and BBC Sounds URLs.
- [x] When the option is disabled, leave BBC URLs unqueued; keep current YouTube handling unchanged.
- [x] Document the option, its default, and how to change it.
- [x] Add tests for both enabled and disabled behavior.

## 2. Generate get_iplayer PVR files

- [ ] Replace the current BBC download response with generation of `get_iplayer` PVR files.
- [ ] Determine whether each BBC URL represents a single episode or a series, and generate the corresponding PVR definition.
- [ ] Determine whether the requested content is TV or radio and set the PVR definition accordingly.
- [ ] Add tests covering single episodes, series, TV, and radio.

## 3. Import PVR files into the get_iplayer container

- [ ] Update the Docker Compose setup to expose a host-side `incoming` directory to the container.
- [ ] Add a process in the container to monitor `incoming` for new PVR files. Add Python to the image only if the existing container tools are insufficient.
- [ ] Ensure the container user can move files from `incoming` into its PVR directory.
- [ ] Validate each PVR file before moving it into the active PVR directory; decide how invalid files are reported or retained.
- [ ] Confirm the existing scheduled PVR run picks up imported files without requiring a separate trigger.
- [ ] Test import, permissions, validation failure, and scheduled-run pickup.

## 4. Organize completed downloads on the NAS

- [ ] Add a post-download process that moves completed files from the download location to their permanent NAS locations.
- [ ] Identify whether each download is TV or radio before choosing its destination.
- [ ] For TV, use `/druidshare/Video/Drama/<title> (<year>)/` and create missing series directories.
- [ ] For radio, use `/druidshare/AudioBooks/Radio/<title>/` and create missing programme directories.
- [ ] Define how titles and years are obtained, and how existing files or name collisions are handled.
- [ ] Test TV and radio placement, directory creation, and failure/retry behavior.

## Decisions to settle

- [ ] Choose the configuration name and default for enabling BBC URL handling.
- [ ] Define how series PVR files should select episodes and whether they should include future episodes.
- [ ] Confirm how to identify radio versus TV reliably from BBC URLs or metadata.
- [ ] Confirm the container's PVR directory, host/container paths, and ownership required for `incoming`.
- [ ] Define what happens to invalid PVR files and failed post-download moves.
- [ ] Confirm the title/year metadata source and the exact TV directory naming convention.

## Current Docker Compose Setup

Reference configuration before the changes above:

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