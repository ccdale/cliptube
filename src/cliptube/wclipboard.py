import sys
from threading import Event
import time

import ccalogging

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.files import sendFileTo
from cliptube.history import getNewUrls

# ccalogging.setConsoleOut()
ccalogging.setLogFile("/home/chris/log/cliptube.log")
ccalogging.setDebug()
# ccalogging.setInfo()
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
            ev.wait(int(cfg["parcellite"]["sleeptime"]))
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def processNewUrls(urls):
    try:
        log.debug(f"sending {len(urls)} urls to mediaserver.")
        tfn = f"/tmp/{__appname__}.list"
        with open(tfn, "w") as ofn:
            ofn.writelines(urls)
        sendFileTo(tfn)
        log.info(f"sent {len(urls)} urls to mediaserver")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)