import re
import sys

from cliptube import __appname__, __version__, errorExit, errorNotify, errorRaise

# filenames look like this
# Sherlock_Series_1_-_01._A_Study_in_Pink_b00t8wp0_editorial.mp4
# Sherlock_Series_1_-_01._A_Study_in_Pink_b00t8wp0_editorial.srt


def twodigits(val):
    try:
        ival = int(val)
        sval = str(ival)
        return f"{sval:0>2}"
    except Exception as e:
        errorNotify(sys.exc_info()[2], e)


with open("/home/chris/tmp/sherlock-fns", "r") as ifn:
    lines = ifn.readlines()
fns = [x.strip() for x in lines]

bits = re.compile(
    r"^(?P<name>.+)_Series_(?P<series>\d+)_-_(?P<episode>\d+).(?P<title>.+)\.(?P<ext>[a-z0-9]+)$"
)
for fn in fns:
    match = bits.match(fn)
    if match:
        groups = match.groupdict()
        series = twodigits(groups["series"])
        episode = twodigits(groups["episode"])
        name = groups["name"].replace("_", " ").strip()
        title = groups["title"].replace("_", " ").strip()
        print(
            f"mv -v \"{fn}\" \"{name} - {title} - S{series}E{episode}.{groups['ext']}\""
        )

# match = bits.match("Sherlock_Series_1_-_01._A_Study_in_Pink_b00t8wp0_editorial.mp4")
# if match:
#     groups = match.groupdict()
#     series = twodigits(groups["series"])
#     episode = twodigits(groups["episode"])
#     name = groups["name"].replace("_", " ")
#     title = groups["title"].replace("_", " ")
#     print(f"{name} Series {series} Episode {episode} - {title} {groups['ext']}")
