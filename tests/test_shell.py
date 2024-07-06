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

from subprocess import CalledProcessError

import pytest

from cliptube.shell import listCmd, shellCommand


def test_listCmd():
    xstr = "A Long String Or 2"
    res = listCmd(xstr)
    assert res == ["A", "Long", "String", "Or", "2"]


def test_listCmd_withList():
    xl = ["A", "Long", "String", "Or", "2"]
    res = listCmd(xl)
    assert res == xl


def test_shellCommand():
    xstr = "ls /home/chris/"
    out, err = shellCommand(xstr)
    assert "Downloads" in out


def test_shellCommand_fail():
    xstr = "ls /wibble"
    with pytest.raises(CalledProcessError):
        out, err = shellCommand(xstr)


def test_shellCommand_allow_fail():
    xstr = "ls /wibble"
    out, err = shellCommand(xstr, canfail=True)
    assert out == ""
    assert err == "ls: cannot access '/wibble': No such file or directory\n"
