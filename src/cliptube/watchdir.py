import os
from signal import signal, SIGINT
import sys
import threading
import time

import ccalogging
import PySimpleGUIQt as sg

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.shell import shellCommand

ccalogging.setLogFile(f"/home/chris/log/{__appname__}.log")
# ccalogging.setDebug()
ccalogging.setInfo()
log = ccalogging.log

ev = threading.Event()
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
                # with open(fqfn, "r") as ifn:
                #     line = ifn.readline()
                # log.debug(f"read url {line} from {fqfn}")
                cmd = ["yt-dlp", "-a", fqfn]
                log.info(f"shellCommand: {cmd=}")
                cout, cerr = shellCommand(cmd)
                log.debug(f"{cout=}")
                log.debug(f"{cerr=}")
                log.info(f"deleting incoming file {fqfn}")
                os.unlink(fqfn)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchDir(path, sleeptime=60):
    try:
        log.debug(f"watch dir {__version__} starting to watch {path}")
        while not ev.is_set():
            getFiles(path)
            ev.wait(sleeptime)
        log.debug("watch dir completed")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def dirWatch():
    try:
        log.info(f"starting {__appname__} {__version__} dirWatch")
        cfg = readConfig()
        path = os.path.abspath(os.path.expanduser(f"~/{cfg['youtube']['incomingdir']}"))
        log.info(f"dirWatch will watch {path}")
        watchDir(path)
        log.info("dirWatch completed")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def doTray():
    try:
        global ev
        # wayland check for QT
        xserver = os.environ.get("XDG_SESSION_TYPE", "Xorg")
        if xserver == "wayland":
            os.environ["QT_QPA_PLATFORM"] = "wayland"
        fred = Thread(target=dirWatch, args=[])
        fred.start()
        log.info(f"Starting tray icon for {__appname__} mediaserver directory watcher")
        menudef = ["E&xit"]
        tray = sg.SystemTray(
            menu=menudef,
            filename=r"image/dirwatch-green.png",
            tooltip=f"{__appname__} directory watcher",
        )
        while True:
            menuitem = tray.read()
            if menuitem == "Exit":
                ev.set()
                break
        log.info("removing tray icon for directory watcher")
        log.info("waiting for thread to end")
        fred.join()
        log.info("thread has ended")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
