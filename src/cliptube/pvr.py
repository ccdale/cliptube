"""Parse BBC programme URLs and write get_iplayer PVR files."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PVR_DIRECTORY = "/mnt/nas/docker/get_iplayer/config/.get_iplayer/pvr"
PVR_FILE_UID = 1000
PVR_FILE_GID = 1000

_BBC_PATH = re.compile(
    r"/(?P<platform>iplayer|sounds)/(?P<mode>episodes|episode|brand|play)/"
    r"(?P<pid>[a-z0-9]{8})(?:/[^?#]*)?/?"
)
_PROGRAMME_TYPES = {
    ("iplayer", "episodes"): ("tv", True),
    ("iplayer", "episode"): ("tv", False),
    ("sounds", "brand"): ("radio", True),
    ("sounds", "play"): ("radio", False),
}


@dataclass(frozen=True)
class BBCProgramme:
    """PVR details extracted from a supported BBC programme URL."""

    pid: str
    media_type: str
    recursive: bool

    def to_pvr_text(self):
        lines = [f"pid {self.pid}"]
        if self.recursive:
            lines.append("pidrecursive 1")
        lines.append(f"type {self.media_type}")
        return "\n".join(lines) + "\n"


def parse_bbc_url(url):
    """Parse a BBC TV/radio episode or series URL into its PVR details."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "bbc.co.uk",
        "www.bbc.co.uk",
    }:
        raise ValueError(f"Unsupported BBC URL: {url}")

    match = _BBC_PATH.fullmatch(parsed.path)
    if match is None:
        raise ValueError(f"Unsupported BBC URL: {url}")

    details = match.groupdict()
    programme_type = _PROGRAMME_TYPES.get((details["platform"], details["mode"]))
    if programme_type is None:
        raise ValueError(f"Unsupported BBC URL: {url}")

    media_type, recursive = programme_type
    return BBCProgramme(details["pid"], media_type, recursive)


def write_pvr_file(
    url,
    output_directory=DEFAULT_PVR_DIRECTORY,
    uid=PVR_FILE_UID,
    gid=PVR_FILE_GID,
):
    """Write a PVR file for a supported BBC URL and set its owner and group."""
    programme = parse_bbc_url(url)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    pvr_path = output_path / programme.pid
    pvr_path.write_text(programme.to_pvr_text(), encoding="utf-8")
    os.chown(pvr_path, uid, gid)
    return pvr_path