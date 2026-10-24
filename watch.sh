#!/usr/bin/env bash
# watch.sh: tail the hook log while the game runs.
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/runtime.py" watch
