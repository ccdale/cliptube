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

from fabric import Connection

from cliptube import errorNotify
from cliptube.config import ConfigFileNotFound, readConfig, writeConfig


def getOutputFileName(cfg):
    try:
        # cfg = readConfig()
        fnum = int(cfg["youtube"]["filenumber"])
        nextn = fnum + 1
        if nextn > 99:
            nextn = 0
        cfg["youtube"]["filenumber"] = str(nextn)
        writeConfig(cfg)
        idir = os.path.abspath(os.path.expanduser(f'~/{cfg["youtube"]["incomingdir"]}'))
        return f"{idir}/{fnum:0>2}"
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def sendFileTo(fn):
    try:
        cfg = readConfig()
        mhost = cfg["mediaserver"]["host"]
        muser = cfg["mediaserver"]["user"]
        mkeyfn = os.path.abspath(
            os.path.expanduser(f'~/.ssh/{cfg["mediaserver"]["keyfn"]}')
        )
        ckwargs = {"key_filename": mkeyfn}
        ofn = getOutputFileName(cfg)
        with Connection(host=mhost, user=muser, connect_kwargs=ckwargs) as c:
            c.put(fn, ofn)
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def homeDir():
    try:
        return os.path.expandvars("$HOME")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


def dirFileList(path):
    try:
        if os.path.isdir(path):
            return [
                f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))
            ]
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
