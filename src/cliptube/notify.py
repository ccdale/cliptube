#
# Copyright (c) 2023-2024, Chris Allison
#
#     This file is part of cliptube.
#
#     cliptube is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     cliptube is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cliptube.  If not, see <http://www.gnu.org/licenses/>.
#
import sys

import ccalogging
from ccalogging import log
from inotify_simple import INotify, flags

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import ConfigFileNotFound, expandPath, readConfig, writeConfig


def directoryWatches(testing=None):
    try:
        # set up logging to stdout as this is a systemd service
        ccalogging.setConsoleOut(STDOUT=True, cformt="%(message)s")
        if testing is not None:
            ccalogging.setDebug()
            log.info(
                f"{__appname__} {__version__} directoryWatches starting in testing mode"
            )
            log.debug(f"test directories: {testing}")
            videodir = testing["videos"]
            playlistdir = testing["playlists"]
            iplayerdir = testing["iplayer"]
        else:
            log.info(f"{__appname__} {__version__} directoryWatches starting")
            cfg = readConfig()
            videodir = expandPath(f'~/{cfg["mediaserver"]["videodir"]}')
            playlistdir = expandPath(f'~/{cfg["mediaserver"]["playlistdir"]}')
            iplayerdir = expandPath(f'~/{cfg["mediaserver"]["iplayerdir"]}')
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)


if __name__ == "__main__":
    try:
        # debug logging when run as a script
        ccalogging.setDebug()
        directoryWatches()
    except Exception as e:
        errorExit(sys.exc_info()[2], e)
