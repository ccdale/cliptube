import os
import sys

import ccalogging

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.history import checkUrl

log = ccalogging.log


def readHistoryFile():
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
