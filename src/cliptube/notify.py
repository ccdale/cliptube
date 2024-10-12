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
import select
import signal
import sys
import threading

import ccalogging
from ccalogging import log
from inotify_simple import INotify, flags, masks

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import ConfigFileNotFound, expandPath, readConfig, writeConfig
from cliptube.files import dirFileList
import cliptube.shell as shell


def interruptNotify(signrcvd, frame):
    try:
        global ev
        signame = signal.Signals(signrcvd).name
        msg = f"signal {signame} ({signrcvd}) received, shutting down..."
        log.info(msg)
        ev.set()
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


# catch sigterm and sigint
signal.signal(signal.SIGINT, interruptNotify)
signal.signal(signal.SIGTERM, interruptNotify)

# event to signal the process to stop
ev = threading.Event()
ev.clear()


class InotifyThread(threading.Thread):
    def __init__(self, path):
        self.xpath = path

        # Initialize the parent class
        threading.Thread.__init__(self)

        # Create an inotify object
        self.xin = INotify()

        # Create a pipe
        self.readfd, write_fd = os.pipe()
        self.__write = os.fdopen(write_fd, "wb")

    def run(self):
        """Override this method in your subclass"""
        # Watch the current directory
        self.xin.add_watch(self.xpath, masks.ALL_EVENTS)

        while True:
            # Wait for inotify events or a write in the pipe
            rlist, _, _ = select.select([self.xin.fileno(), self.readfd], [], [])

            # Print all inotify events
            if self.xin.fileno() in rlist:
                for event in self.xin.read(timeout=0):
                    xflags = [f.name for f in flags.from_mask(event.mask)]
                    print(f"{event} {xflags}")

            # Close everything properly if requested
            if self.readfd in rlist:
                os.close(self.readfd)
                self.xin.close()
                return

    def stop(self):
        # Request for stop by writing in the pipe
        if not self.__write.closed:
            self.__write.write(b"\x00")
            self.__write.close()


class DirectoryWatcher(InotifyThread):
    def __init__(self, path, cmd=["yt-dlp", "-a", "<fqfn>"], readfiles=False):
        super().__init__(path)
        self.__cmd = cmd
        self.readfiles = readfiles

    def run(self):
        # Watch the current directory,
        # wait for new files to be created, written to and closed
        self.xin.add_watch(self.xpath, flags.CLOSE_WRITE)
        # super(InotifyThread, self).xin.add_watch(self.xpath, masks.CLOSE)

        while True:
            # Wait for inotify events or a write in the pipe
            rlist, _, _ = select.select([self.xin.fileno(), self.readfd], [], [])

            # Print all inotify events and execute the action
            if self.xin.fileno() in rlist:
                for event in self.xin.read(timeout=0):
                    xflags = [f.name for f in flags.from_mask(event.mask)]
                    print(f"{event} {xflags}")
                    self.action(event)

            # Close everything properly if requested
            if self.readfd in rlist:
                os.close(self.readfd)
                self.xin.close()
                return

    def action(self, event):
        try:
            # pause the current inotify thread
            print("pausing inotify")
            self.xin.rm_watch(self.xin.fileno())
            files = dirFileList(self.xpath, filterext=[".err"])
            # need to weed out '.err' files
            while files is not None and len(files) > 0:
                # loop through each file found
                # pass the fqfn to the command
                for fn in files:
                    fqfn = os.path.join(self.xpath, fn)
                    if self.readfiles:
                        if not self.doFileContents(fqfn):
                            os.rename(fqfn, f"{fqfn}.err")
                        else:
                            print(f"deleting incoming file {fqfn}")
                            os.unlink(fqfn)
                # have another look to see if there are more files
                files = dirFileList(self.xpath, filterext=[".err"])
        except Exception as e:
            # unknown error
            print(f"error: {e}")
        finally:
            # restart the inotify thread
            print("restarting inotify")
            self.xin.add_watch(self.xpath, flags.CLOSE_WRITE)

    def readFile(self, fqfn):
        with open(fqfn, "r") as ifn:
            lines = ifn.readlines()
            urls = [x.strip() for x in lines]
        return urls

    def doFileContents(self, fqfn):
        urls = self.readFile(fqfn)
        for url in urls:
            scmd = [x if x != "<fqfn>" else url for x in self.__cmd]
            try:
                sout, serr = shell.shellCommand(scmd)
            except Exception as e:
                # cmd exited with an error
                print(f"{scmd} exited with an error {e}")
                return False
        return True


def directoryWatches(testing=None):
    try:
        # set up logging to stdout as this is a systemd service
        ccalogging.setConsoleOut(STDOUT=True, cformat="%(message)s")
        if testing is not None:
            ccalogging.setDebug()
            log.info(
                f"{__appname__} {__version__} directoryWatches starting in testing mode"
            )
            log.debug(f"test directories: {testing}")
            videodir = testing["videos"]
            playlistdir = testing["playlists"]
            iplayerdir = testing["iplayer"]
        else:
            log.info(f"{__appname__} {__version__} directoryWatches starting")
            cfg = readConfig()
            videodir = expandPath(f'~/{cfg["mediaserver"]["videodir"]}')
            playlistdir = expandPath(f'~/{cfg["mediaserver"]["playlistdir"]}')
            iplayerdir = expandPath(f'~/{cfg["mediaserver"]["iplayerdir"]}')
            dvw = DirectoryWatcher(videodir, cmd=["yt-dlp", "-a", "<fqfn>"])
            dvw.start()
            dpw = DirectoryWatcher(iplayerdir, cmd=["get_iplayer", "--url", "<fqfn>"])
            dpw.start()
            while not ev.is_set():
                ev.wait()
            dvw.stop()
            dpw.stop()
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)


if __name__ == "__main__":
    try:
        directoryWatches(testing=True)
    except Exception as e:
        errorExit(sys.exc_info()[2], e)
