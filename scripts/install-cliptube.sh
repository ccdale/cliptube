#!/bin/bash

set -e

if [ $UID -eq 0 ]; then
    echo "Must be run as a normal user, not root."
    exit 1
fi

ROOT=$(git rev-parse --show-toplevel)
DATADIR=$ROOT/configs

CONFFN=$HOME/.config/cliptube.cfg

if [ ! -r $CONFFN ]; then
    cp $DATADIR/cliptube.cfg $CONFFN
fi

SRVDIR=$HOME/.config/systemd/user

# make the needed directory layout
mkdir -p $SRVDIR

# copy the config
cp $DATADIR/cliptube.service $SRVDIR/

# setup to start on user login
systemctl --user enable cliptube.service

# run now
systemctl --user start cliptube.service

