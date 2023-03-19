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

"""config module for cliptube application."""
import configparser
from pathlib import Path
import sys

from cliptube import errorNotify


class ConfigFileNotFound(Exception):
    pass


def readConfig(appname):
    try:
        cfgpath = Path(f"~/.config/{appname}.cfg")
        if not cfgpath.exists():
            raise ConfigFileNotFound(f"cannot find config file: {cfgpath}")
        config = configparser.ConfigParser()
        config.read(cfgpath)
        return config
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)
