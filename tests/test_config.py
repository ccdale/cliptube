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

"""test module for the cliptube.config module"""
import os

import pytest

from cliptube import __appname__
from cliptube.config import ConfigFileNotFound, readConfig, writeConfig


def test_expandPath():
    tilde = "~/"
    home = os.path.abspath(os.path.expanduser(tilde))
    assert home == expandPath(tilde)


def test_readConfig():
    cfg = readConfig()
    assert cfg["mediaserver"]["user"] == "chris"


def test_readConfig_does_not_exist(capsys):
    junkname = "does_not_existify"
    with pytest.raises(ConfigFileNotFound):
        junk = readConfig(overrideappname=junkname)


def test_writeConfig():
    cfg = readConfig()
    fv = int(cfg["testsection"]["fileval"])
    fv += 1
    cfg["testsection"]["fileval"] = str(fv)
    writeConfig(cfg)
    xcfg = readConfig()
    xfv = int(cfg["testsection"]["fileval"])
    assert xfv == fv
