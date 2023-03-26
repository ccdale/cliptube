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

import sys

import pyclip

from cliptube import __version__, errorExit, errorNotify, errorRaise
from cliptube.config import readConfig

appname = "cliptube"


def goBabe():
    try:
        print(f"{appname} {__version__} starting")
        cfg = readConfig(appname)
    except Exception as e:
        errorExit(sys.exc_info()[2], e)
