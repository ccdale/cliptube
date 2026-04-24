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
    raise


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
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True)  # noqa: E501
            .splitlines()
            .pop()
        )
    except Exception as e:
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
    except Exception as e:
        errorExit(sys.exc_info()[2], e)
        return "0.0.0"


class colours:
    """
    Colours class: provides ANSI escape codes for terminal text formatting.
    Use colours.fg.<colour> for foreground and colours.bg.<colour>
    for background. Also provides formatting options like bold, underline, etc.
    """

    reset = "\033[0m"
    bold = "\033[01m"
    disable = "\033[02m"
    underline = "\033[04m"
    reverse = "\033[07m"
    strikethrough = "\033[09m"
    invisible = "\033[08m"

    class fg:
        """Foreground colour codes."""

        black = "\033[30m"
        red = "\033[31m"
        green = "\033[32m"
        orange = "\033[33m"
        blue = "\033[34m"
        purple = "\033[35m"
        cyan = "\033[36m"
        lightgray = "\033[37m"
        darkgray = "\033[90m"
        lightred = "\033[91m"
        lightgreen = "\033[92m"
        yellow = "\033[93m"
        lightblue = "\033[94m"
        pink = "\033[95m"
        lightcyan = "\033[96m"

    class bg:
        """Background colour codes."""

        black = "\033[40m"
        red = "\033[41m"
        green = "\033[42m"
        orange = "\033[43m"
        blue = "\033[44m"
        purple = "\033[45m"
        cyan = "\033[46m"
        lightgray = "\033[47m"


def progressBar(
    progress,
    total,
    showValues=False,
    remove=False,
    newline=False,
    colour=colours.fg.green,
    bgcolour=colours.fg.darkgray,
):
    """
    Display a progress bar in the terminal.

    Args:
        progress (int): Current progress value.
        total (int): Total value for completion.
        showValues (bool): If True, show progress/total values.
        remove (bool): If True, remove the progress bar after completion.
        newline (bool): If True, print a newline after removing the bar.
    """
    try:
        percent = 100 * (progress / float(total))
        fill = chr(9609)  # left 3/4 filled block
        blank = chr(9617)  # light shaded character
        blanks = blank * (100 - int(percent))
        fills = fill * int(percent)
        bar = f"{colour}{fills}{bgcolour}{blanks}"
        if showValues:
            msg = f"\r|{bar}| {progress} / {total}"
        else:
            msg = f"\r|{bar}| {percent:.2f}"
        print(msg, end="\r")
        if remove:
            splat = " " * len(msg)
            if newline:
                print(f"{colours.reset}{splat}")
            else:
                print(f"{colours.reset}{splat}", end="\r")
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


__version__ = getVersion()
