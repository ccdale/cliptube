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
import os
import tempfile
import time

import pytest

from cliptube import __appname__, __version__
import cliptube.notify as notify


def test_directoryWatches(capsys):
    testdirs = {"videos": "videos", "playlists": "playlists", "iplayer": "iplayer"}
    with tempfile.TemporaryDirectory() as tmpd:
        for k, v in testdirs.items():
            tp = os.path.join(tmpd, v)
            os.makedirs(tp)
            testdirs[k] = tp
        notify.directoryWatches(testdirs)
    out, err = capsys.readouterr()
    assert (
        f"{__appname__} {__version__} directoryWatches starting in testing mode\n"
        in out
    )
    assert f"test directories: {testdirs}\n" in out


def test_DirectoryWatcher(capsys):
    with tempfile.TemporaryDirectory() as tmpd:
        xcmd = ["ls", "-l"]
        dw = notify.DirectoryWatcher(tmpd, cmd=xcmd)
        dw.start()
        with open(os.path.join(tmpd, "testfile"), "w") as f:
            f.write("test")
        # captured = capsys.readouterr()
        # print(f"{captured=}")
        # allow time for the thread to notice
        time.sleep(1)
        dw.stop()
        captured2 = capsys.readouterr()
        print(f"{captured2=}")
        assert "testfile" in captured2.out


# this doesn't work as expected as we are not trying to test
# the main process but the thread, which doesn't appear to be
# captured.
# def test_DirectoryWatcher_no_cmd(capsys):
#     with tempfile.TemporaryDirectory() as tmpd:
#         with pytest.raises(Exception):
#             dw = notify.DirectoryWatcher(tmpd)
#             dw.start()
#             with open(os.path.join(tmpd, "testfile"), "w") as f:
#                 f.write("test")
#             # allow time for the thread to notice
#             time.sleep(1)
#             dw.stop()
#         captured = capsys.readouterr()
#         assert "CLOSE_WRITE" in captured.out
#         assert "exited with an error" in captured.err
#         assert "testfile" in captured.out
