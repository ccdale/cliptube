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
ccalogging.setLogFile("/home/chris/log/cliptube.log")
# ccalogging.setDebug()
ccalogging.setInfo()
log = ccalogging.log

# exitflag = False
ev = Event()
ev.clear()


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


def watchparcellite():
    try:
        log.info(f"{__appname__} {__version__} starting - CTRL-C to exit")
        cfg = readConfig()
        while not ev.is_set():
            urls = getNewUrls()
            if len(urls):
                log.debug(f"watchparcellite: {len(urls)} new urls found")
                processNewUrls(urls)
            log.debug(f'sleeping for {cfg["parcellite"]["sleeptime"]} seconds')
            ev.wait(float(cfg["parcellite"]["sleeptime"]))
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
        # wayland check for QT
        xserver = os.environ.get("XDG_SESSION_TYPE", "Xorg")
        if xserver == "wayland":
            os.environ["QT_QPA_PLATFORM"] = "wayland"
        fred = Thread(target=watchparcellite, args=[])
        fred.start()
        log.info("Starting tray icon for cliptube")
        menudef = ["E&xit"]
        tray = sg.SystemTray(menu=menudef, filename=r"image/cliptube.png", tooltip="Youtube clipboard watcher")
        while True:
            menuitem = tray.read()
            if menuitem = "Exit":
                ev.set()
                break
        log.info("removing tray icon for cliptube")
        log.info("waiting for thread to end")
        fred.join()
        log.info("thread has ended")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
