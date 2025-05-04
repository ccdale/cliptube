#!/bin/bash

set -e

if [ $UID -eq 0 ]; then
    echo "Must be run as a normal user, not root."
    exit 1
fi

# goto the users home directory
cd

SRVDIR=$HOME/.config/systemd/user

# make the needed directory layout
mkdir -p $SRVDIR

# copy the config
cp configs/dirwatch.service $SRVDIR/

# setup to start on user login
systemctl --user enable dirwatch.service

# run now
systemctl --user start dirwatch.service
