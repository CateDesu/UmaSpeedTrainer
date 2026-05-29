#!/usr/bin/env bash
# setspeed.sh: change Uma Musume speed at runtime.
# Usage:
#   setspeed.sh 2          # 2x
#   setspeed.sh 0.5        # half speed (slow-mo)
#   setspeed.sh off        # back to 1.0 (passthrough)
#   setspeed.sh            # show current
set -u
CTRL="${UMA_HOOK_CTRL:-/tmp/uma-hook.ctrl}"

case "${1:-}" in
    "")
        if [[ -r "$CTRL" ]]; then
            printf 'current: %sx\n' "$(cat "$CTRL")"
        else
            printf 'ctrl file not present (%s)\n' "$CTRL" >&2; exit 1
        fi
        ;;
    off|reset|1|1.0|1.00)
        printf '1.0' > "$CTRL"
        echo 'speed: OFF (1.0x, passthrough)'
        ;;
    *)
        # Validate it parses as a positive number.
        if ! awk -v v="$1" 'BEGIN { if (v+0 <= 0 || v+0 > 1000) exit 1 }'; then
            echo "invalid speed: $1 (must be > 0 and <= 1000)" >&2; exit 1
        fi
        printf '%s' "$1" > "$CTRL"
        echo "speed: ${1}x  (takes effect within ~100 ms)"
        ;;
esac
