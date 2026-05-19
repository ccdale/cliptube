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

"""subprocess commands to send via a shell."""

import os
import re
import subprocess
import sys
from subprocess import CalledProcessError

from cliptube import errorRaise


def listCmd(cmd):
    """ensures the passed in command is a list not a string."""
    try:
        if type(cmd) is not list:
            if type(cmd) is not str:
                raise Exception(
                    f"cmd should be list or string, you gave {type(cmd)} {cmd}"
                )
            else:
                cmd = cmd.strip().split(" ")
        return cmd
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)


def shellCommand(cmd, canfail=False):
    """Runs the shell command cmd

    returns a tuple of (stdout, stderr) or None
    raises an exception if subprocess returns a non-zero exitcode
    """
    ret = None
    try:
        cmd = listCmd(cmd)
        # print(" ".join(cmd))
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if not canfail:
            # raise an exception if cmd returns an error code
            ret.check_returncode()
        return (ret.stdout, ret.stderr)
    except CalledProcessError as e:
        stderr = ret.stderr if ret else "N/A"
        stdout = ret.stdout if ret else "N/A"
        msg = f"ERROR: {stderr}\nstdout: {stdout}"
        msg += f"\nCommand was:\n{' '.join(cmd)}"
        print(msg)
        errorRaise(sys.exc_info()[2], e)
    except Exception as e:
        stderr = ret.stderr if ret else "N/A"
        stdout = ret.stdout if ret else "N/A"
        msg = f"ERROR: {stderr}\nstdout: {stdout}"
        msg += f"\nCommand was:\n{' '.join(cmd)}"
        print(msg)
        errorRaise(sys.exc_info()[2], e)


def getMergerOutputLine(stdout, stderr):
    """Return the last yt-dlp merger line from stdout/stderr, if present."""
    merger_lines = []
    for stream in [stdout, stderr]:
        if stream is None:
            continue
        for line in str(stream).splitlines():
            stripped = line.strip()
            if stripped.startswith("[Merger]"):
                merger_lines.append(stripped)
    return merger_lines[-1] if merger_lines else None


def getMergerOutputFilename(stdout, stderr):
    """Return merged output filename basename from yt-dlp output, if present."""
    merger_line = getMergerOutputLine(stdout, stderr)
    if merger_line is None:
        return None

    # yt-dlp merger output includes the target path in quotes.
    match = re.search(r'"([^"]+)"', merger_line)
    if match is None:
        match = re.search(r"'([^']+)'", merger_line)
    if match is None:
        return None
    return os.path.basename(match.group(1))
