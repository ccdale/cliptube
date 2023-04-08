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
from queue import Queue
import sys
import time
from threading import Event, Thread
from urllib.parse import urlparse, parse_qs

import ccalogging
import pyclip

# import PySimpleGUIQt as sg


from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig
from cliptube.files import sendFileTo


# appname = "cliptube"
ccalogging.setConsoleOut()
ccalogging.setDebug()
# ccalogging.setInfo()
log = ccalogging.log


class ClipboardTimeout(Exception):
    pass


def goBabe():
    try:
        log.debug(f"{__appname__} {__version__} starting")
        cfg = readConfig(__appname__)
        # layout = [[psg.Button("OK"), psg.Button("Cancel")]
        magic = "STOPCLIPBOARDWATCH"
        # lines = []
        log.info(f"Copy '{magic}' to the clipboard to stop watching the clipboard")
        pyclip.clear()
        while True:
            txt = waitForClipboard()
            # txt = pyperclip.waitForNewPaste()
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
                    saveUrl(url)
                    # log.debug(f"storing '{url}'")
                    # lines.append(url)
        # with open("/home/chris/batch", "w") as ofn:
        #     for line in lines:
        #         ofn.write(f"{line}\n")
        log.debug(f"{__appname__} terminating")
    except Exception as e:
        errorExit(sys.exc_info()[2], e)


def saveUrl(url):
    try:
        log.debug(f"saving youtube url {url}")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


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
                raise ClipboardTimeout(
                    f"Timeout in waitForClipboard after {time.time() - stime:<2} seconds"
                )
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)


def watchClipboard(Q, ev, magic="STOPCLIPBOARDWATCH"):
    try:
        while True:
            try:
                txt = waitForClipboard(timeout=1)
            except ClipboardTimeout:
                if ev.is_set():
                    Q.put("STOP")
                    break
                continue
            if magic in txt:
                break
            url = checkUrl(txt)
            if url is not None:
                Q.put(url)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def checkUrl(txt):
    try:
        if "youtube.com" in txt and "watch" in txt:
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


def watchQ(Q):
    try:
        while True:
            if Q.empty():
                time.sleep(1)
            else:
                iurl = Q.get()
                if "STOP" in iurl:
                    Q.task_done()
                    break
                sendUrl(iurl)
                Q.task_done()
        return cn
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def sendUrl(iurl):
    try:
        fn = f"/tmp/{__appname__}.dat"
        with open(fn, "w") as ofn:
            ofn.write(iurl)
        sendFileTo(fn)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def main():
    try:
        msg = f"{__appname__} {__version__} watching clipboard for youtube urls"
        log.info(msg)
        ev = Event()
        ev.clear()
        Q = Queue()
        kwargs = {"magic": "STOPCLIPBOARDWATCH"}
        wcfred = Thread(target=watchClipboard, args=[Q, ev], kwargs=kwargs)
        wcfred.start()
        wqfred = Thread(target=watchQ, args=[Q])
        wqfred.start()
        wcfred.join()
        wqfred.join()
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
