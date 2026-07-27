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


class InvalidCommandType(TypeError):
    """Raised when a shell command is not a string or a list."""


def listCmd(cmd):
    """ensures the passed in command is a list not a string."""
    if isinstance(cmd, list):
        return cmd
    if isinstance(cmd, str):
        return cmd.strip().split(" ")
    raise InvalidCommandType(
        f"cmd should be list or string, you gave {type(cmd)} {cmd}"
    )


def shellCommand(cmd, canfail=False, process_callback=None):
    """Runs the shell command cmd with optional process tracking.

    Args:
        cmd: Command as string or list
        canfail: If False, raise exception on non-zero exit
        process_callback: Optional callable(process) to store the Popen object

    returns a tuple of (stdout, stderr)
    raises an exception if subprocess returns a non-zero exitcode
    """
    ret = None
    proc = None
    try:
        cmd = listCmd(cmd)
        # Use Popen instead of run() to track and manage the process
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        # Notify caller of the process object for potential interruption
        if process_callback is not None:
            process_callback(proc)
        stdout, stderr = proc.communicate()
        if not canfail and proc.returncode != 0:
            ret = type("obj", (object,), {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr})()
            ret.check_returncode = lambda: proc.check_returncode()
            raise CalledProcessError(proc.returncode, cmd)
        return (stdout, stderr)
    except CalledProcessError as e:
        stdout_text = stdout if proc else "N/A"
        stderr_text = stderr if proc else "N/A"
        msg = f"ERROR: {stderr_text}\nstdout: {stdout_text}"
        msg += f"\nCommand was:\n{' '.join(cmd)}"
        print(msg)
        errorRaise(sys.exc_info()[2], e)
    except (InvalidCommandType, OSError, TypeError, ValueError) as e:
        stdout_text = stdout if proc else "N/A"
        stderr_text = stderr if proc else "N/A"
        msg = f"ERROR: {stderr_text}\nstdout: {stdout_text}"
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
