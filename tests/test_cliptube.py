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
    assert __version__ == "0.1.0"


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
