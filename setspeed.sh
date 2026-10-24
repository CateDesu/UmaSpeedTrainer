#!/usr/bin/env bash
# setspeed.sh: change Uma Musume speed at runtime.
# Usage:
#   setspeed.sh 2          # 2x
#   setspeed.sh 0.5        # half speed (slow-mo)
#   setspeed.sh off        # back to 1.0 (passthrough)
#   setspeed.sh            # show current
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/runtime.py" speed "$@"
