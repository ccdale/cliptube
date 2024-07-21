#
# Copyright (c) 2023-2024, Chris Allison
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
from signal import signal, SIGINT
import time
from threading import Event, Thread
from urllib.parse import urlparse, parse_qs

import ccalogging
import pyclip

import PySimpleGUIQt as sg


from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import expandPath, readConfig
from cliptube.files import sendFileTo
from cliptube.history import checkUrl


# appname = "cliptube"
# ccalogging.setConsoleOut()
logfile = expandPath(f"~/log/{__appname__}.log")
ccalogging.setLogFile(logfile)
ccalogging.setDebug()
# ccalogging.setInfo()
log = ccalogging.log


def interruptCT(signrcvd, frame):
    try:
        print()
        print("Keyboard interrupt received in ct module - exiting.")
        print()
        sys.exit(255)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


# if we get a `ctrl-c` from the keyboard, stop immediately
# by going to the interruptCT above
signal(SIGINT, interruptCT)


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
                # raise ClipboardTimeout(
                #     f"Timeout in waitForClipboard after {time.time() - stime:<2} seconds"
                # )
                break
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)


def watchClipboard(Q, ev, magic="STOPCLIPBOARDWATCH"):
    try:
        log.debug("watchclipboard thread starting")
        while True:
            if ev.is_set():
                break
            txt = waitForClipboard(timeout=1)
            if txt is not None and magic in txt:
                log.debug(f"{magic} found. clipboard watcher thread closing")
                Q.put("STOP")
                ev.set()
                break
            url, vtype = checkUrl(txt)
            if url is not None:
                # sendUrl(url)
                log.debug(f"putting {url} on Q")
                Q.put(url)
        log.debug("watch clipboard thread complete")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def watchQ(Q, ev):
    try:
        log.debug("watch Q thread starting")
        while True:
            if ev.is_set():
                break
            if Q.empty():
                time.sleep(1)
            else:
                iurl = Q.get()
                if "STOP" in iurl:
                    log.debug("STOP found in Q, closing Q watcher")
                    Q.task_done()
                    ev.set()
                    break
                log.debug(f"sending {iurl} to media server")
                sendUrl(iurl)
                Q.task_done()
        log.debug("watch Q thread complete")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def sendUrl(iurl):
    try:
        fn = f"/tmp/{__appname__}.dat"
        with open(fn, "w") as ofn:
            ofn.write(iurl)
        sendFileTo(fn)
        log.info(f"sent {iurl} to druidmedia")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def main():
    try:
        msg = f"{__appname__} {__version__} watching clipboard for youtube urls"
        log.info(msg)
        # wayland check for QT
        xserver = os.environ.get("XDG_SESSION_TYPE", "Xorg")
        if xserver == "wayland":
            os.environ["QT_QPA_PLATFORM"] = "wayland"
        pyclip.clear()
        ev = Event()
        ev.clear()
        Q = Queue()
        kwargs = {"magic": "STOPCLIPBOARDWATCH"}
        wcfred = Thread(target=watchClipboard, args=[Q, ev], kwargs=kwargs)
        wcfred.start()
        wqfred = Thread(target=watchQ, args=[Q, ev])
        wqfred.start()

        menu_def = [
            "BLANK",
            ["&Status", "---", "&Load Queue", "Save &Queue", "---", "E&xit"],
        ]
        tray = sg.SystemTray(
            menu=menu_def,
            filename=r"image/cliptube.png",
            tooltip="Youtube URL clipboard watcher",
        )

        while True:  # event loop
            menuitem = tray.read()
            if menuitem == "Exit":
                pyclip.copy("STOPCLIPBOARDWATCH")
                ev.set()
                break

        wcfred.join()
        wqfred.join()
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
