#!/usr/bin/env bash
# watch.sh — colorize the hook log while the game runs.
LOG="${UMA_HOOK_LOG:-/tmp/uma-hook.log}"
echo "Tailing $LOG  (Ctrl-C to stop)"
exec tail -F "$LOG"
