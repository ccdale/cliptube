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
