#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PATH="$HERE/usr/bin:$PATH"
export PYTHONHOME="$HERE/usr"
export PYTHONPATH="$HERE/usr/lib/python3/dist-packages:$PYTHONPATH"
exec "$HERE/usr/bin/python3" "$HERE/usr/src/main_launcher.py" "$@"
