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

from cliptube import errorNotify
from cliptube.config import ConfigFileNotFound, readConfig, writeConfig


def getOutputFileName():
    try:
        cfg = readConfig()
        fnum = cfg["youtube"]["filenumber"]
        ifnum = int(fnum) + 1
        cfg["youtube"]["filenumber"] = str(ifnum)
        writeConfig(cfg)
        idir = os.path.abspath(os.path.expanduser(f'~/{cfg["youtube"]["incomingdir"]}'))
        return f"{idir}/{fnum:0>3}"
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
