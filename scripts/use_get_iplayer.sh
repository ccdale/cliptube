#!/bin/bash

set -e

# -o|outputdir for output directory
# -u|url for url

OUTPUTDIR=
URL=

TEMP=$(getopt -o o:u: --long outputdir:,url: -n 'use_get_iplayer.sh' -- "$@")

if [ $? -ne 0 ]; then
	echo 'Terminating...' >&2
	exit 1
fi

# Note the quotes around "$TEMP": they are essential!
eval set -- "$TEMP"
unset TEMP

while true; do
	case "$1" in
        '-o'|'--outputdir')
            OUTPUTDIR="$2"
            shift 2
            continue
        ;;
        '-u'|'--url')
            URL="$2"
            shift 2
            continue
        ;;
        '--')
            shift
            break
        ;;
        *)
            echo 'Internal error!' >&2
            exit 1
        ;;
    esac
done

[ -z "$OUTPUTDIR" ] && echo "Output directory is required" && exit 1
[ -z "$URL" ] && echo "URL is required" && exit 1

echo "OUTPUTDIR: $OUTPUTDIR"

if [ ! -d "$OUTPUTDIR" ]; then
    echo "Output directory does not exist: $OUTPUTDIR"
    exit 1
fi

echo "URL: $URL"

cd "$OUTPUTDIR"

get_iplayer --url "$URL" --subtitles
