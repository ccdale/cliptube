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

import pytest

from cliptube import errorExit, errorNotify, errorRaise, __version__


class TheException(Exception):
    """A test Exception.
    Args:
        Exception:
    """

    pass


def test_cliptube_version():
    assert __version__ == "0.2.4"


def test_errorNotify(capsys):
    try:
        msg = "This is the test exception"
        raise TheException(msg)
    except Exception as e:
        exci = sys.exc_info()[2]
        lineno = exci.tb_lineno
        fname = exci.tb_frame.f_code.co_name
        ename = type(e).__name__
        errorNotify(exci, e)
    finally:
        emsg = f"{ename} Exception at line {lineno} in function {fname}: {msg}\n"
        out, err = capsys.readouterr()
        assert out == emsg


def test_errorRaise(capsys):
    """It raises the TheException Exception after printing the error."""
    try:
        msg = "This is the test exception"
        raise TheException(msg)
    except Exception as e:
        exci = sys.exc_info()[2]
        lineno = exci.tb_lineno
        fname = exci.tb_frame.f_code.co_name
        ename = type(e).__name__
        with pytest.raises(TheException):
            errorRaise(exci, e)
    finally:
        emsg = f"{ename} Exception at line {lineno} in function {fname}: {msg}\n"
        out, err = capsys.readouterr()
        assert out == emsg


def test_errorExit(capsys):
    """It attempts sys.exit after printing the error."""
    try:
        msg = "This is the test exception"
        raise TheException(msg)
    except Exception as e:
        exci = sys.exc_info()[2]
        lineno = exci.tb_lineno
        fname = exci.tb_frame.f_code.co_name
        ename = type(e).__name__
        with pytest.raises(SystemExit):
            errorExit(exci, e)
    finally:
        emsg = f"{ename} Exception at line {lineno} in function {fname}: {msg}\n"
        out, err = capsys.readouterr()
        assert out == emsg
