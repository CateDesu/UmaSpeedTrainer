# uma_hook — runtime-toggleable speedhack for Uma Musume Pretty Derby (Proton)

LD_PRELOAD hook that intercepts glibc time/sleep functions. Wine's `ntdll.so`
imports `clock_gettime`/`gettimeofday`/`time`/`usleep` from glibc, with zero
inline `syscall` instructions, so all Windows time APIs (`QueryPerformanceCounter`,
`GetTickCount64`, `timeGetTime`, etc.) inside the Unity game route through
our replacements. Confirmed for Proton 10, 11, Experimental, GE-Proton, and
proton-cachyos-slr.

## Quick start

1. Steam → Umamusume: Pretty Derby → Properties → Launch Options:
   ```
   /home/cate/uma_hook/launch.sh %command%
   ```
2. Launch. The hook loads at **1.0x** (passthrough) so the game boots normally.
3. Once you're in a section that benefits from speed (training, races, etc.):
   ```
   /home/cate/uma_hook/setspeed.sh 3
   ```
4. Before any loading screen / menu transition / network sync:
   ```
   /home/cate/uma_hook/setspeed.sh off
   ```

Speed change is picked up within ~100 ms by every Wine thread; the hook
re-anchors all monotonic clocks at the moment of change so time never jumps
or moves backwards.

## What gets scaled / what doesn't

| clock | scaled? | reason |
|---|---|---|
| `CLOCK_MONOTONIC` / `_RAW` / `_COARSE` | yes | what Wine routes QPC, GetTickCount, timeGetTime to |
| `CLOCK_BOOTTIME` | yes | Wine GetTickCount64 path |
| `CLOCK_REALTIME` / `_COARSE` | **no** | wall clock; scaling breaks TLS certs and server time-skew checks |
| `gettimeofday`, `time` | **no** | wall clock |
| `nanosleep`, `clock_nanosleep`, `usleep` | yes (inverse) | 100 ms sleep at 3x becomes a real 33 ms sleep |

Wall-clock paths are still **counted and logged** for diagnosis, just not
manipulated.

## Files

| file | purpose |
|---|---|
| `libuma_hook.c` | source |
| `lib64/libuma_hook.so` | 64-bit hook |
| `lib/libuma_hook.so` | 32-bit hook (Steam wrappers like `steam-launch-wrapper`) |
| `launch.sh` | Steam wrapper: composes LD_PRELOAD, exports env, resets ctrl to 1.0 |
| `setspeed.sh` | runtime control: `setspeed.sh 3`, `setspeed.sh off` |
| `watch.sh` | `tail -F` the log |

## Env knobs (all in `launch.sh`)

| var | default | meaning |
|---|---|---|
| `UMA_HOOK_FILTER` | `UmamusumePrettyDerby.exe` | substrings of `/proc/self/cmdline` that activate the hook |
| `UMA_HOOK_CTRL` | `/tmp/uma-hook.ctrl` | speed control file |
| `UMA_HOOK_LOG` | `/tmp/uma-hook.log` | log file |
| `UMA_HOOK_QUIET` | `0` | set to `1` to suppress per-call logs |
| `UMA_SPEED` | `1.0` | initial speed if ctrl file is missing |

## Anti-cheat note

Uma Musume's checks are mostly server-side. Keeping wall clock untouched
defangs the obvious time-skew detection. Risk on your main account is
non-zero; the user has accepted that.
