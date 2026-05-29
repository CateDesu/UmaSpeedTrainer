#!/usr/bin/env bash
# launch.sh — Steam launch wrapper for the uma_hook LD_PRELOAD.
#
# Steam Properties → Launch Options:
#   /home/cate/uma_hook/launch.sh %command%
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Provide both arches as separate entries; ld.so silently skips the
# wrong-class one for each process (same trick Steam uses for gameoverlayrenderer).
HOOK_ENTRY="$HOOK_DIR/lib64/libuma_hook.so:$HOOK_DIR/lib/libuma_hook.so"

# --- knobs ---
# Initial speed is 1.0 (passthrough) so the game finishes loading at real
# time. Use setspeed.sh to bump it during gameplay; reset to 1.0 before
# returning to any loading screen or network sync.
: "${UMA_SPEED:=1.0}"
: "${UMA_HOOK_CTRL:=/tmp/uma-hook.ctrl}"
: "${UMA_HOOK_LOG:=/tmp/uma-hook.log}"
: "${UMA_HOOK_QUIET:=0}"
: "${UMA_HOOK_FILTER:=UmamusumePrettyDerby.exe}"

export UMA_SPEED UMA_HOOK_CTRL UMA_HOOK_LOG UMA_HOOK_QUIET UMA_HOOK_FILTER

# Initialize ctrl file to 1.0 each launch so a stale 5.0 from last session
# doesn't kick in before the user wants it.
echo "1.0" > "$UMA_HOOK_CTRL"

# Compose LD_PRELOAD:
#   1) APPEND our entry so gameoverlayrenderer stays first (avoids CRT crash on
#      Arch/CachyOS where the overlay expects to lead the chain).
#   2) Strip leading/trailing/duplicate ':' to avoid empty entries — newer
#      glibcs occasionally bail on those.
clean_preload() {
    local p="${1:-}"
    # collapse runs of ':' and strip leading/trailing ones
    p="${p//::/:}"
    p="${p#:}"
    p="${p%:}"
    printf '%s' "$p"
}

OLD="$(clean_preload "${LD_PRELOAD:-}")"
if [[ -n "$OLD" ]]; then
    export LD_PRELOAD="${OLD}:${HOOK_ENTRY}"
else
    export LD_PRELOAD="$HOOK_ENTRY"
fi

# Start each launch with a fresh log.
: > "$UMA_HOOK_LOG"

{
    printf '[launch.sh] PID=%d  speed=%s  filter=%s  log=%s\n' \
           "$$" "$UMA_SPEED" "$UMA_HOOK_FILTER" "$UMA_HOOK_LOG"
    printf '[launch.sh] LD_PRELOAD=%s\n' "$LD_PRELOAD"
    printf '[launch.sh] argv:'
    printf ' %q' "$@"
    printf '\n\n'
} >> "$UMA_HOOK_LOG"

exec "$@"
