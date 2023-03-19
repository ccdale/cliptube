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

"""test module for the cliptube.config module"""
import pytest

from cliptube.config import ConfigFileNotFound, readConfig


def test_readConfig_does_not_exist(capsys):
    appname = "does_not_existify"
    junk = readConfig(appname)
    out, err = capsys.readouterr()
    assert "ConfigFileNotFound" in out
    assert "cannot find config file" in out
    assert f"{appname}.cfg" in out
