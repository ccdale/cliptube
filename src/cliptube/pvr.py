"""Parse BBC programme URLs and write get_iplayer PVR files."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PVR_DIRECTORY = "/mnt/nas/docker/get_iplayer/config/.get_iplayer/pvr"

_PID = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_PROGRAMME_TYPES = {
    ("iplayer", "episodes"): ("tv", True),
    ("iplayer", "episode"): ("tv", False),
    ("sounds", "brand"): ("radio", True),
    ("sounds", "play"): ("radio", False),
}


def is_bbc_programme_url(url):
    """Return whether a URL is under a BBC TV or Sounds programme path."""
    parsed = urlparse(url.strip())
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"bbc.co.uk", "www.bbc.co.uk"}
        and parsed.path.startswith(("/iplayer/", "/sounds/"))
    )


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
    if not is_bbc_programme_url(url):
        raise ValueError(f"Unsupported BBC URL: {url}")

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 3:
        raise ValueError(f"Unsupported BBC URL: {url}")

    platform, mode, pid = path_parts[:3]
    programme_type = _PROGRAMME_TYPES.get((platform, mode))
    if programme_type is None:
        raise ValueError(f"Unsupported BBC URL: {url}")
    if not _PID.fullmatch(pid):
        raise ValueError(f"Unsupported BBC URL: {url}")

    media_type, recursive = programme_type
    return BBCProgramme(pid.lower(), media_type, recursive)


def write_pvr_file(
    url,
    output_directory=DEFAULT_PVR_DIRECTORY,
):
    """Write a PVR file for a supported BBC URL."""
    programme = parse_bbc_url(url)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    pvr_path = output_path / programme.pid
    pvr_path.write_text(programme.to_pvr_text(), encoding="utf-8")
    return pvr_path