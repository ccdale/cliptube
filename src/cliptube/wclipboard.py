import os
import sys
from signal import SIGINT, SIGTERM, signal
from threading import Event

import ccalogging  # type: ignore

from cliptube import (
    __appname__,
    __version__,
    errorExit,
    errorNotify,
    localqueue,
    log,
)
from cliptube.config import readConfig
from cliptube.history import getNewUrls

ccalogging.setConsoleOut()
# logfile = os.path.abspath(os.path.expanduser(f"~/log/{__appname__}.log"))
# ccalogging.setLogFile(logfile)
# ccalogging.setDebug()
ccalogging.setInfo()

# exitflag = False
ev = Event()
ev.clear()


class onlyOne(Exception):
    pass


def interruptWP(signrcvd, frame):
    ev.set()


# if we get a `ctrl-c` from the keyboard, stop immediately
# by going to the interruptCT above
signal(SIGINT, interruptWP)
signal(SIGTERM, interruptWP)


def checkForNewUrls():
    urls = getNewUrls()
    if len(urls):
        log.debug(f"watchclipboard: {len(urls)} new urls found")
        processNewUrls(urls)


def watchparcellite():
    try:
        log.info(f"{__appname__} {__version__} starting - Interrupt to exit")
        cfg = readConfig()
        while not ev.is_set():
            checkForNewUrls()
            log.debug(f"sleeping for {cfg['parcellite']['sleeptime']} seconds")
            ev.wait(float(cfg["parcellite"]["sleeptime"]))
        # final check before exiting
        log.info("Final check for urls before shutting down")
        checkForNewUrls()
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:  # noqa: BLE001
        errorNotify(sys.exc_info()[2], e)


def watchCopyQ():
    try:
        log.info(f"{__appname__} {__version__} starting - Interrupt to exit")
        cfg = readConfig()
        while not ev.is_set():
            checkForNewUrls()
            log.debug(f"sleeping for {cfg['parcellite']['sleeptime']} seconds")
            ev.wait(float(cfg["parcellite"]["sleeptime"]))
        # final check before exiting
        log.info("Final check for urls before shutting down")
        checkForNewUrls()
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:  # noqa: BLE001
        errorNotify(sys.exc_info()[2], e)


def watchGnomeClipboard():
    processor = None
    try:
        pidfn = "/tmp/cliptube.pid"
        oneOnly(pidfn)
        log.info(f"{__appname__} {__version__} starting - Interrupt to exit")
        cfg = readConfig()
        # Initialize the local queue processor
        processor = localqueue.initialize(num_workers=1, restore_from_cache=True)
        while not ev.is_set():
            checkForNewUrls()
            log.debug(f"sleeping for {cfg['gnomeclipindicator']['sleeptime']} seconds")
            ev.wait(float(cfg["gnomeclipindicator"]["sleeptime"]))
        # final check before exiting
        log.info("Final check for urls before shutting down")
        checkForNewUrls()
        # Gracefully shutdown the processor
        if processor:
            processor.shutdown(timeout=90, wait_for_current=True)
        if os.path.exists(pidfn):
            try:
                os.unlink(pidfn)
            except OSError as e:
                log.error(f"Error deleting pid file: {e}")
        log.info(f"{__appname__} closing down, bye.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(pidfn):
            try:
                os.unlink(pidfn)
            except OSError as cleanup_err:
                log.error(
                    f"Error deleting pid file during exception handling: {cleanup_err}"
                )
        # Ensure processor shutdown even on error
        if processor:
            try:
                processor.shutdown(timeout=5, wait_for_current=False)
            except Exception as shutdown_err:  # noqa: BLE001
                log.error(f"Error during processor shutdown: {shutdown_err}")
        errorExit(sys.exc_info()[2], e)


def sortUrls(urls):
    plists = []
    iplayer = []
    videos = []
    for url in urls:
        if "playlist" in url:
            log.debug(f"playlist url found: {url}")
            plists.append(url)
        elif "iplayer" in url:
            iplayer.append(url)
    videos.extend([x for x in urls if x not in plists and x not in iplayer])
    return plists, iplayer, videos


def processVideoUrls(videos):
    log.debug(f"queueing {len(videos)} video urls for local processing.")
    localqueue.queue_urls(videos, vtype="v")
    log.info(f"queued {len(videos)} video urls for processing")


def processPlaylistUrls(videos):
    log.debug(f"queueing {len(videos)} playlist urls for local processing.")
    localqueue.queue_urls(videos, vtype="p")
    log.info(f"queued {len(videos)} playlist urls for processing")


def processIPlayerUrls(videos):
    log.debug(f"queueing {len(videos)} iplayer urls for local processing.")
    localqueue.queue_urls(videos, vtype="i")
    log.info(f"queued {len(videos)} iplayer urls for processing")


def processNewUrls(urls):
    plists, iplayer, videos = sortUrls(urls)
    if len(videos):
        processVideoUrls(videos)
    if len(plists):
        processPlaylistUrls(plists)
    if len(iplayer):
        processIPlayerUrls(iplayer)


def oneOnly(pidfn):
    if os.path.exists(pidfn):
        ipid = checkPid(pidfn)
        if ipid:
            raise onlyOne(f"{__appname__} is already running with pid {ipid}")
    with open(pidfn, "w") as ofn:
        log.info("Writing pid file")
        ofn.write(f"{os.getpid()}\n")
    with open(pidfn, "r") as ifn:
        pidn = ifn.read()
        log.info(f"running pid, read from pid file is {pidn}")


def checkPid(pidfn):
    """checks that the pid in file pidfn is still running, pidfn should exist"""
    with open(pidfn, "r") as ifn:
        pidn = ifn.read().strip()
    ipid = int(pidn)
    try:
        os.kill(ipid, 0)
        return ipid
    except OSError:
        log.info(f"previous pid {pidn} not running")
        return None
