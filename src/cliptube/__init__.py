import subprocess
import sys
import tomllib
from pathlib import Path

import ccalogging

__appname__ = "cliptube"

log = ccalogging.log


def errorNotify(exci, e, fname=None):
    lineno = exci.tb_lineno
    if fname is None:
        fname = exci.tb_frame.f_code.co_name
    ename = type(e).__name__
    msg = f"{ename} Exception at line {lineno} in function {fname}: {e}"
    log.error(msg)


def errorRaise(exci, e, fname=None):
    errorNotify(exci, e, fname)
    raise e


def errorExit(exci, e, fname=None):
    errorNotify(exci, e, fname)
    sys.exit(1)


def gitroot() -> str:
    """
    Get the root directory of the current git repository.
    Returns:
        str: Path to the root directory of the git repository.
    """
    try:
        return (
            subprocess
            .check_output(["git", "rev-parse", "--show-toplevel"], text=True)
            .splitlines()
            .pop()
        )
    except (subprocess.CalledProcessError, OSError) as e:
        errorExit(sys.exc_info()[2], e)
        return ""


def getVersion() -> str:
    """
    Get the version of the project from pyproject.toml.
    Returns:
        str: The version string.
    """
    try:
        git_root = gitroot()
        if not git_root:
            return "0.0.0"
        pyproject_path = Path(git_root) / "pyproject.toml"
        if not pyproject_path.exists():
            return "0.0.0"
        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)
        return pyproject_data.get("project", {}).get("version", "0.0.0")
    except (OSError, tomllib.TOMLDecodeError) as e:
        errorExit(sys.exc_info()[2], e)
        return "0.0.0"


__version__ = getVersion()
