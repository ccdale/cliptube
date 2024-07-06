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
import re

from cliptube.config import ConfigFileNotFound, readConfig
from cliptube.files import getOutputFileName, homeDir


def test_homeDir():
    homed = homeDir()
    assert os.path.abspath(os.path.expanduser("~")) == homed


def test_getOutputFileName():
    homed = homeDir()
    cfg = readConfig()
    ofn = getOutputFileName(cfg, vtype="v")
    assert ofn.startswith(f"{homed}/.cliptube/videos")
    ofn = getOutputFileName(cfg, vtype="p")
    assert ofn.startswith(f"{homed}/.cliptube/playlists")
    ofn = getOutputFileName(cfg, vtype="i")
    assert ofn.startswith(f"{homed}/.cliptube/iplayer")
