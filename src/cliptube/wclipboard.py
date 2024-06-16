import os
from signal import signal, SIGINT
import sys
from threading import Event, Thread
import time

import ccalogging
import PySimpleGUIQt as sg

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.files import sendFileTo
from cliptube.history import getNewUrls

# ccalogging.setConsoleOut()
logfile = os.path.abspath(os.path.expanduser(f"~/log/{__appname__}.log"))
ccalogging.setLogFile(logfile)
# ccalogging.setDebug()
ccalogging.setInfo()
log = ccalogging.log

# exitflag = False
ev = Event()
ev.clear()


class onlyOne(Exception):
    pass


def interruptWP(signrcvd, frame):
    try:
        global ev
        msg = "Keyboard interrupt received in wclipboard module - exiting."
        log.info(msg)
        ev.set()
        # sys.exit(255)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


# if we get a `ctrl-c` from the keyboard, stop immediately
# by going to the interruptCT above
signal(SIGINT, interruptWP)


def checkForNewUrls():
    try:
        urls = getNewUrls()
        if len(urls):
            log.debug(f"watchclipboard: {len(urls)} new urls found")
            processNewUrls(urls)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchparcellite():
    try:
        log.info(f"{__appname__} {__version__} starting - CTRL-C to exit")
        cfg = readConfig()
        while not ev.is_set():
            checkForNewUrls()
            log.debug(f'sleeping for {cfg["parcellite"]["sleeptime"]} seconds')
            ev.wait(float(cfg["parcellite"]["sleeptime"]))
        # final check before exiting
        log.info("Final check for urls before shutting down")
        checkForNewUrls()
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchCopyQ():
    try:
        log.info(f"{__appname__} {__version__} starting - CTRL-C to exit")
        cfg = readConfig()
        while not ev.is_set():
            checkForNewUrls()
            log.debug(f'sleeping for {cfg["parcellite"]["sleeptime"]} seconds')
            ev.wait(float(cfg["parcellite"]["sleeptime"]))
        # final check before exiting
        log.info("Final check for urls before shutting down")
        checkForNewUrls()
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchGnomeClipboard():
    try:
        log.info(f"{__appname__} {__version__} starting - CTRL-C to exit")
        cfg = readConfig()
        while not ev.is_set():
            checkForNewUrls()
            log.debug(f'sleeping for {cfg["gnomeclipindicator"]["sleeptime"]} seconds')
            ev.wait(float(cfg["gnomeclipindicator"]["sleeptime"]))
        # final check before exiting
        log.info("Final check for urls before shutting down")
        checkForNewUrls()
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def processNewUrls(urls):
    try:
        log.debug(f"sending {len(urls)} urls to mediaserver.")
        tfn = f"/tmp/{__appname__}.list"
        with open(tfn, "w") as ofn:
            ofn.write("\n".join(urls))
            ofn.write("\n")
            # ofn.writelines(urls)
        sendFileTo(tfn)
        log.info(f"sent {len(urls)} urls to mediaserver")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def doTray():
    try:
        global ev
        pidfn = "/tmp/cliptube.pid"
        oneOnly(pidfn)
        # wayland check for QT
        xserver = os.environ.get("XDG_SESSION_TYPE", "Xorg")
        if xserver == "wayland":
            os.environ["QT_QPA_PLATFORM"] = "wayland"
        # fred = Thread(target=watchCopyQ, args=[])
        fred = Thread(target=watchGnomeClipboard, args=[])
        fred.start()
        log.info(f"Starting tray icon for {__appname__}")
        menudef = ["BLANK", ["E&xit"]]
        iconfn = os.path.abspath(
            os.path.expanduser(r"~/.local/share/image/cliptube.png")
        )
        tray = sg.SystemTray(
            menu=menudef,
            filename=iconfn,
            tooltip="Youtube clipboard watcher",
        )
        while True:
            menuitem = tray.read()
            if menuitem == "Exit":
                ev.set()
                break
        log.info("removing tray icon for cliptube")
        log.info("waiting for thread to end")
        fred.join()
        log.info("thread has ended")
        log.info(f"deleting pid file {pidfn}")
        os.unlink(pidfn)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def oneOnly(pidfn):
    try:
        if os.path.exists(pidfn):
            ipid = checkPid(pidfn)
            if ipid != False:
                raise onlyOne(f"{__appname__} is already running with pid {ipid}")
        with open(pidfn, "w") as ofn:
            log.info("Writing pid file")
            ofn.write(f"{os.getpid()}\n")
        with open(pidfn, "r") as ifn:
            pidn = ifn.read()
            log.info(f"running pid, read from pid file is {pidn}")
    except Exception as e:
        errorExit(sys.exc_info()[2], e)


def checkPid(pidfn):
    """checks that the pid in file pidfn is still running, pidfn should exist"""
    try:
        with open(pidfn, "r") as ifn:
            pidn = ifn.read()
            try:
                os.kill(int(pidn), 0)
                return int(pidn)
            except OSError:
                log.info(f"previous pid {pidn} not running")
                return False
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)
    finally:
        return False
