import os
import sys
from urllib.parse import urlparse, parse_qs

import ccalogging

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.shell import shellCommand

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
        elif txt is not None and "youtu.be" in txt:
            return txt.strip()
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def saveList(urls):
    try:
        fn = os.path.abspath(os.path.expanduser(f"~/.config/{__appname__}.list"))
        log.debug(f"{len(urls)} urls saved to {__appname__} history")
        with open(fn, "w") as ofn:
            ofn.write("\n".join(urls))
            ofn.write("\n")
            # ofn.writelines(urls)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def readList():
    try:
        xlist = []
        fn = os.path.abspath(os.path.expanduser(f"~/.config/{__appname__}.list"))
        if os.path.exists(fn):
            with open(fn, "r") as ifn:
                # strip the newline of the end of each line as it comes in
                xlist = [x.strip() for x in ifn.readlines()]
        log.debug(f"{len(xlist)} urls read from {__appname__} history")
        return xlist
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def getNewUrls():
    try:
        xlist = readList()
        log.debug(f"{xlist=}")
        # hlist = readParcelliteHistoryFile()
        hlist = readParcelliteHistory()
        log.debug(f"{hlist=}")
        nlist = [x for x in hlist if x not in xlist]
        log.debug(f"{nlist=}")
        saveList(hlist)
        log.debug(f"{len(nlist)} new urls found")
        return nlist
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def readParcelliteHistory():
    try:
        urls = []
        cmd = ["parcellite", "-c"]
        xout, xerr = shellCommand(cmd)
        lines = [x.strip() for x in xout.split("\n")]
        for line in lines:
            if line.startswith("http"):
                url = checkUrl(line)
                if url is not None:
                    urls.append(url)
        log.debug(f"{len(urls)} urls found in parcellite history file")
        return urls
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def readParcelliteHistoryFile():
    try:
        cfg = readConfig()
        histfile = os.path.abspath(os.path.expanduser(cfg["parcellite"]["histfile"]))
        with open(histfile, "r") as ifn:
            hist = ifn.readlines()
        lines = hist[0].split("\x00")
        log.debug(f"{len(lines)} lines in parcellite history file")
        urls = []
        for line in lines:
            if line.startswith("http"):
                url = checkUrl(line)
                if url is not None:
                    urls.append(url)
        log.debug(f"{len(urls)} urls found in parcellite history file")
        return urls
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
