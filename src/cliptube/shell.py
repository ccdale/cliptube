"""subprocess commands to send via a shell."""
import sys
import subprocess
from subprocess import CalledProcessError

from cliptube import errorRaise


def listCmd(cmd):
    """ensures the passed in command is a list not a string."""
    try:
        if type(cmd) != list:
            if type(cmd) != str:
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
    try:
        cmd = listCmd(cmd)
        # print(" ".join(cmd))
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if not canfail:
            # raise an exception if cmd returns an error code
            ret.check_returncode()
        return (ret.stdout, ret.stderr)
    except CalledProcessError as e:
        msg = f"ERROR: {ret.stderr}\nstdout: {ret.stdout}"
        msg += f"\nCommand was:\n' '.join(cmd)"
        print(msg)
        errorRaise(sys.exc_info()[2], e)
    except Exception as e:
        errorRaise(sys.exc_info()[2], e)
