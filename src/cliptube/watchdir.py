import os
import sys
import threading
import time

import ccalogging

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.shell import shellCommand

ccalogging.setLogFile(f"/home/chris/log/{__appname__}.log")
ccalogging.setDebug()
log = ccalogging.log


def dirFileList(path):
    try:
        if os.path.isdir(path):
            return [
                f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))
            ]
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def getFiles(path):
    try:
        files = dirFileList(path)
        if files is not None:
            for fn in files:
                fqfn = os.path.join(path, fn)
                log.debug(f"found incoming file {fqfn}")
                with open(fqfn, "r") as ifn:
                    line = ifn.readline()
                log.debug(f"read url {line} from {fqfn}")
                cmd = ["yt-dlp", line]
                log.debug(f"shellCommand: {cmd=}")
                cout, cerr = shellCommand(cmd)
                log.debug(f"{cout=}")
                log.debug(f"{cerr=}")
                log.debug(f"deleting incoming file {fqfn}")
                os.unlink(fqfn)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchDir(ev, path, sleeptime=60):
    try:
        log.debug(f"watch dir starting to watch {path}")
        while not ev.is_set():
            getFiles(path)
            time.sleep(sleeptime)
        log.debug("watch dir completed")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def dirWatch():
    try:
        log.debug(f"starting {__appname__} {__version__} dirWatch")
        cfg = readConfig()
        path = os.path.abspath(os.path.expanduser(f"~/{cfg['youtube']['incomingdir']}"))
        log.debug(f"dirWatch will watch {path}")
        ev = threading.Event()
        ev.clear()
        watchDir(ev, path)
        log.debug("dirWatch completed")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
