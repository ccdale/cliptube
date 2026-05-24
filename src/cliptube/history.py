import json
import os
import sys
from urllib.parse import parse_qs, urlparse

import ccalogging

from cliptube import __appname__, errorNotify
from cliptube.config import expandPath, readConfig

log = ccalogging.log


def checkUrl(txt):
    try:
        if txt is None:
            return None

        if "youtube.com" in txt and "watch" in txt:
            log.debug(f"detected youtube url '{txt}'")
            parsed = urlparse(txt)
            dparsed = parse_qs(parsed.query)
            log.debug(f"{dparsed=}")
            if "v" in dparsed:
                vid = dparsed["v"][0]
                log.debug(f"video {vid} extracted from url")
                return f"https://www.youtube.com/watch?v={vid}"
        if (
            "youtu.be" in txt
            or ("youtube.com" in txt and "shorts" in txt)
            or ("youtube.com" in txt and "playlist" in txt)
            or "bbc.co.uk/iplayer" in txt
        ):
            return txt.strip()
        return None
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def saveList(urls):
    try:
        fn = expandPath(f"~/.config/{__appname__}.list")
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
        fn = expandPath(f"~/.config/{__appname__}.list")
        if os.path.exists(fn):
            with open(fn, "r") as ifn:
                xlist = [x.strip() for x in ifn]
        log.debug(f"{len(xlist)} urls read from {__appname__} history")
        return xlist
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def getNewUrls():
    try:
        xlist = readList()
        log.debug(f"{xlist=}")
        hlist = readGnomeClipIndicatorFile()
        log.debug(f"{hlist=}")
        nlist = [x for x in hlist if x not in xlist]
        log.debug(f"{nlist=}")
        saveList(hlist)
        log.debug(f"{len(nlist)} new urls found")
        return nlist
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def readGnomeClipIndicatorFile():
    try:
        cfg = readConfig()
        histfile = expandPath(cfg["gnomeclipindicator"]["histfile"])
        with open(histfile, "r") as ifn:
            hist = json.load(ifn)
        lines = [x["contents"] for x in hist if x["contents"].startswith("http")]
        urls = []
        for line in lines:
            url = checkUrl(line)
            if url is not None:
                urls.append(url)
        return urls
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
