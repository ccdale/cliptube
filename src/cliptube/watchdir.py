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
import os
from signal import signal, SIGINT
import sys
from threading import Event
import time

import daemon
import ccalogging
from ccalogging import log

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import expandPath, readConfig
from cliptube.files import dirFileList
from cliptube.shell import shellCommand

# log = None

ev = Event()
ev.clear()


def interruptWD(signrcvd, frame):
    try:
        global ev
        msg = "Keyboard interrupt received in watchdir module - exiting."
        log.info(msg)
        ev.set()
        # sys.exit(255)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


# if we get a `ctrl-c` from the keyboard, stop immediately
# by going to the interruptCT above
signal(SIGINT, interruptWD)


def getVideos(path):
    try:
        if path.endswith("iplayer"):
            scmd = ["get_iplayer", "--url"]
        else:
            scmd = ["yt-dlp"]
        files = dirFileList(path)
        if files is not None:
            for fn in files:
                fqfn = os.path.join(path, fn)
                log.debug(f"found incoming file {fqfn}")
                with open(fqfn, "r") as ifn:
                    tlines = ifn.readlines()
                lines = [x.strip() for x in tlines]
                log.debug(f"read {len(lines)} url(s) from {fqfn}")
                log.debug(f"{lines=}")
                for lin in lines:
                    try:
                        cmd = scmd.copy()
                        cmd.append(lin)
                        log.info(f"shellCommand: {cmd=}")
                        cout, cerr = shellCommand(cmd)
                        log.debug(f"{cout=}")
                        log.debug(f"{cerr=}")
                        log.info(f"deleting incoming file {fqfn}")
                        os.unlink(fqfn)
                    except Exception as e:
                        log.error(f"shellCommand {cmd} exited with an error {e}")
                        os.move(fqfn, f"{fqfn}.err")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchDir(path, sleeptime=60):
    try:
        log.debug(f"watch dir {__version__} starting to watch {path}")
        while not ev.is_set():
            getVideos(path)
            ev.wait(sleeptime)
        log.debug("watch dir completed")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchDirectories(paths, sleeptime=60):
    try:
        log.debug(f"watch directories {__version__} starting to watch {paths}")
        if isinstance(paths, str):
            paths = [paths]
        while not ev.is_set():
            for path in paths:
                getVideos(path)
            ev.wait(sleeptime)
        log.debug("watch directories completed")
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)


def getWatchPath(cfg):
    try:
        xp = cfg["youtube"]["incomingdir"]
        if xp.startswith("/"):
            return xp
        return expandPath(f"~/{xp}")
    except Exception as e:
        errorExit(sys.exc_info()[2], e)


def dirWatch():
    try:
        log.info(f"starting {__appname__} {__version__} directoriesWatch")
        cfg = readConfig()
        paths = []
        paths.append(expandPath(f'~/{cfg["mediaserver"]["videodir"]}'))
        paths.append(expandPath(f'~/{cfg["mediaserver"]["playlistdir"]}'))
        paths.append(expandPath(f'~/{cfg["mediaserver"]["iplayerdir"]}'))
        log.info(f"directoriesWatch will watch {paths}")
        watchDirectories(paths)
        log.info("directoriesWatch completed")
    except Exception as e:
        errorExit(sys.exc_info()[2], e)


def daemonDirWatch():
    try:
        # global log
        with daemon.DaemonContext():
            logfile = expandPath(f"~/log/{__appname__}-watchdir.log")
            ccalogging.setLogFile(logfile)
            # ccalogging.setDebug()
            ccalogging.setInfo()
            log = ccalogging.log
            log.debug(f"{__appname__}-watchdir deamonised!")
            dirWatch()
    except Exception as e:
        errorExit(sys.exc_info()[2], e)
