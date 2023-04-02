#
# Copyright (c) 2023, Chris Allison
#
#     This file is part of cliptube.
#
#     cliptube is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     cliptube is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cliptube.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import sys
import time
from urllib.parse import urlparse, parse_qs

import ccalogging
from fabric import Connection
import pyclip

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig


# appname = "cliptube"
ccalogging.setConsoleOut()
ccalogging.setDebug()
# ccalogging.setInfo()
log = ccalogging.log


def goBabe():
    try:
        log.debug(f"{__appname__} {__version__} starting")
        cfg = readConfig(__appname__)
        magic = "STOPCLIPBOARDWATCH"
        lines = []
        log.info(f"Copy '{magic}' to the clipboard to stop watching the clipboard")
        pyclip.clear()
        while True:
            txt = waitForClipboard()
            log.debug(f"text from clipboard '{txt}'")
            if magic in txt:
                break
            if "youtube.com" in txt and "watch" in txt:
                log.debug(f"detected youtube url '{txt}'")
                parsed = urlparse(txt)
                dparsed = parse_qs(parsed.query)
                log.debug(f"{dparsed=}")
                if "v" in dparsed:
                    vid = dparsed["v"][0]
                    log.debug(f"video {vid} extracted from url")
                    url = f"https://www.youtube.com/watch?v={vid}"
                    log.debug(f"storing '{url}'")
                    lines.append(url)
        with open("/home/chris/batch", "w") as ofn:
            for line in lines:
                ofn.write(f"{line}\n")
        log.debug(f"{__appname__} terminating")
    except Exception as e:
        errorExit(sys.exc_info()[2], e)


def waitForClipboard(timeout=None):
    try:
        stime = time.time()
        while True:
            txt = pyclip.paste(text=True)
            if txt != "":
                pyclip.clear()
                return txt.strip()
            time.sleep(0.01)
            if timeout is not None and time.time() > (stime + timeout):
                raise Exception(
                    f"Timeout in waitForClipboard after {time.time() - stime:<2} seconds"
                )
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def sendFileTo(cfg, fn, ofn):
    try:
        mhost = cfg["mediaserver"]["host"]
        muser = cfg["mediaserver"]["user"]
        mkeyfn = os.path.abspath(
            os.path.expanduser(f'~/.ssh/{cfg["mediaserver"]["keyfn"]}')
        )
        ckwargs = {"key_filename": keyfn}
        with Connection(host=mhost, user=muser, connect_kwargs=ckwargs) as c:
            c.put(fn, ofn)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
