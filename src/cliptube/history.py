import os
import sys

import ccalogging

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.parcellite import readHistoryFile

log = ccalogging.log


def checkUrl(txt):
    try:
        if txt is not None and "youtube.com" in txt and "watch" in txt:
            log.debug(f"detected youtube url '{txt}'")
            parsed = urlparse(txt)
            dparsed = parse_qs(parsed.query)
            log.debug(f"{dparsed=}")
            if "v" in dparsed:
                vid = dparsed["v"][0]
                log.debug(f"video {vid} extracted from url")
                return f"https://www.youtube.com/watch?v={vid}"
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def saveList(urls):
    try:
        fn = os.path.abspath(os.path.expanduser(f"~/.config/{__appname__}.list"))
        log.debug(f"{len(urls)} urls saved to {__appname__} history")
        with open(fn, "w") as ofn:
            ofn.writelines(urls)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def readList():
    try:
        xlist = []
        fn = os.path.abspath(os.path.expanduser(f"~/.config/{__appname__}.list"))
        if os.path.exists(fn):
            with open(fn, "r") as ifn:
                xlist = ifn.readlines()
        log.debug(f"{len(xlist)} urls read from {__appname__} history")
        return xlist
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def getNewUrls():
    try:
        xlist = readList()
        hlist = readHistoryFile()
        nlist = [x for x in hlist if x not in xlist]
        saveList(hlist)
        log.debug(f"{len(nlist)} new urls found")
        return nlist
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)