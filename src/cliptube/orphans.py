import mimetypes
import os
import sys

import ccalogging

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig

logfile = os.path.abspath(os.path.expanduser(f"~/log/{__appname__}.log"))
ccalogging.setLogFile(logfile)
ccalogging.setDebug()
# ccalogging.setInfo()
log = ccalogging.log


def getSubsPath(cfg):
    try:
        xp = cfg["mediaserver"]["incomingdir"]
        if xp.startswith("/"):
            return xp
        return os.path.abspath(os.path.expanduser(f"~/{xp}"))
    except Exception as e:
        errorExit(sys.exc_info()[2], e)


def hasVideo(filelist):
    try:
        for f in filelist:
            xtype, xenc = mimetypes.guess_type(f)
            if xtype.startswith("video"):
                return True
        return False
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def findOrphans():
    try:
        log.info(f"starting {__appname__} {__version__} findOrphans")
        cfg = readConfig()
        path = getSubsPath(cfg)
        log.debug(f"changing working directory to {path}")
        os.chdir(path)
        files = os.listdir()
        log.debug(f"found {len(files)} files in {path}")
        entries = {}
        deletelist = []
        for file in files:
            fn, ext = os.path.splitext(file)
            # subtitle files have 2 exts, '.vtt' and a language code
            # i.e. somefile.en-blah.vtt, somefile.en-en.vtt etc
            if ext == ".vtt":
                xfn, xext = os.path.splitext(fn)
                if xext.startswith(".en"):
                    fn = xfn
            if fn not in entries:
                entries[fn] = []
            entries[fn].append(file)
        log.debug(f"found {len(entries.keys())} file sets in {path}")
        for fn in entries:
            log.debug(f"checking whether {fn} has orphaned subtitle files")
            if not hasVideo(entries[fn]):
                log.debug(f"{fn} ({len(entries[fn])} subtitle files) - orphaned")
                deletelist.extend(entries[fn])
        log.info(f"found {len(deletelist)} files to delete")
        log.debug(f"will delete {deletelist}")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
