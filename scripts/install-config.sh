#!/bin/bash

set -e

if [ $UID -eq 0 ]; then
    echo "Must be run as a normal user, not root."
    exit 1
fi

# goto the users home directory
cd


CONFDIR=$HOME/.config

# copy the config
cp configs/cliptube.cfg $CONFDIR/
