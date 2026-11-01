import os
import sys
from signal import SIGINT, SIGTERM, signal
from threading import Event

import ccalogging  # type: ignore

from cliptube import (
    __appname__,
    __version__,
    errorExit,
    localqueue,
    log,
)
from cliptube.config import readConfig
from cliptube.history import HistoryStore, extract_urls
from cliptube.pvr import is_bbc_programme_url

ccalogging.setConsoleOut()
# logfile = os.path.abspath(os.path.expanduser(f"~/log/{__appname__}.log"))
# ccalogging.setLogFile(logfile)
# ccalogging.setDebug()
ccalogging.setInfo()

# Global processor reference for signal handler access
processor = None
source = None

# exitflag = False
ev = Event()
ev.clear()


class onlyOne(Exception):
    pass


def interruptWP(signrcvd, frame):
    """Handle SIGINT/SIGTERM by interrupting subprocesses and gracefully shutting down."""
    signame = "SIGINT" if signrcvd == SIGINT else "SIGTERM"
    log.info(f"Received {signame}, initiating graceful shutdown with subprocess interruption...")
    ev.set()
    if source is not None:
        source.wake()


# if we get a `ctrl-c` from the keyboard, stop immediately
# by going to the interruptCT above
def watchClipboard():
    global processor, source
    from cliptube.clipsource import select_source
    from cliptube.config import getClipboardConfig

    pidfn = "/tmp/cliptube.pid"
    owns_pid = False
    ev.clear()
    signal(SIGINT, interruptWP)
    signal(SIGTERM, interruptWP)
    try:
        oneOnly(pidfn)
        owns_pid = True
        log.info(f"{__appname__} {__version__} starting - Interrupt to exit")
        cfg = readConfig()
        options = getClipboardConfig(cfg)
        history = HistoryStore(historydays=options.historydays)
        source = select_source(cfg)
        processor = localqueue.initialize(
            num_workers=1, history=history, on_failure=source.wake, stop_event=ev,
        )
        source.start()
        while not ev.is_set():
            text = source.wait_for_change(None)
            if processor.failed.is_set():
                raise RuntimeError("Download worker failed; check the error log")
            if ev.is_set():
                break
            if text:
                processNewUrls(extract_urls(text))
    except Exception as e:  # noqa: BLE001
        errorExit(sys.exc_info()[2], e)
    finally:
        # Stop downloads before waiting on clipboard helpers.
        try:
            try:
                localqueue.shutdown(timeout=3)
            finally:
                processor = None
                if source is not None:
                    source.stop()
        finally:
            source = None
            if owns_pid and os.path.exists(pidfn):
                os.unlink(pidfn)
        log.info(f"{__appname__} closing down, bye.")


def sortUrls(urls):
    plists = []
    iplayer = []
    radio = []
    videos = []
    for url in urls:
        if "bbc.co.uk/sounds/" in url and is_bbc_programme_url(url):
            radio.append(url)
        elif is_bbc_programme_url(url):
            iplayer.append(url)
        elif "playlist" in url:
            log.debug(f"playlist url found: {url}")
            plists.append(url)
    videos.extend(
        [x for x in urls if x not in plists and x not in iplayer and x not in radio]
    )
    return plists, iplayer, radio, videos


def processVideoUrls(videos):
    log.debug(f"queueing {len(videos)} video urls for local processing.")
    localqueue.queue_urls(videos, vtype="v")
    log.info(f"queued {len(videos)} video urls for processing")


def processPlaylistUrls(videos):
    log.debug(f"queueing {len(videos)} playlist urls for local processing.")
    localqueue.queue_urls(videos, vtype="p")
    log.info(f"queued {len(videos)} playlist urls for processing")


def processNewUrls(urls):
    plists, iplayer, radio, videos = sortUrls(urls)
    if len(videos):
        processVideoUrls(videos)
    if len(plists):
        processPlaylistUrls(plists)
    if iplayer or radio:
        localqueue.queue_urls(iplayer + radio, vtype="b")


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
