# UmaSpeedTrainer

A speed trainer for **Umamusume: Pretty Derby**. Lets you fast forward
through the slow parts of training, races, and menus with an on/off
button.

* Linux (Proton): works. Tested up to 5x with no freezes, no crashes.
* Windows: **UNTESTED. USE AT YOUR OWN RISK.** See the box below.

> [!WARNING]
> ### About the Windows build
>
> Hi, I am Claude, an AI assistant. Cate asked me to make a Windows
> version. I do not own a Windows computer. I do not own the Windows
> version of the game. I do not have the anti cheat shim to bonk
> against. What I do have is the Linux build (which works), a working
> understanding of how PE imports are laid out, and the kind of
> confidence that lets you ship code you have never once executed.
>
> This is, to be fair, fairly normal for me. Someone asks for a thing,
> I produce the thing, the thing may or may not survive contact with
> reality. The Windows build is currently in a quantum superposition
> where it both works and catches fire, and will remain there until a
> real human observes it.
>
> If you observe it and it works, please open an issue, I would
> genuinely like to know. If you observe it and it does not work,
> please also open an issue, with the error message and a screenshot
> if you can. If you observe it and your account gets a strongly
> worded letter from Cygames, I am sorry, you did read this part, but
> I am still sorry.

## How it works

The game asks the operating system "what time is it?" many times per
second. Unity uses the answer to decide how far to advance animations,
physics, timers, and so on. If the answer is a lie about how much time
has passed, the game runs faster (or slower) without knowing.

The trainer does not touch game memory, does not patch the game files,
and does not attach as a debugger. It only intercepts the system time
functions in a library the game loads. The Linux build does this with
`LD_PRELOAD`. The Windows build does it with a DLL that patches the
import tables of the modules already loaded into the game.

There is one control file. The trainer reads it every 100 milliseconds.
The GUI, the command line script, and the .bat file all just write a
number into that file. To turn off the speed up, write `1.0`.

## Linux setup (Proton)

```
cd ~/uma_hook
make
```

In Steam, right click Umamusume: Pretty Derby, open Properties, and put
this in Launch Options:

```
/home/cate/uma_hook/launch.sh %command%
```

That is the only setup step. The game launches at normal speed every
time. The trainer is loaded but does nothing until you tell it to.

### Control it

Three options, pick whichever you like.

GUI:
```
python3 /home/cate/uma_hook/gui.py
```
A small window with ON, OFF, and a speed picker. Stays on top of the
game. To pin it to your KDE app launcher:
```
cp uma-hook.desktop ~/.local/share/applications/
```

Command line:
```
./setspeed.sh 3        # 3x
./setspeed.sh 0.5      # half speed
./setspeed.sh off      # back to normal
./setspeed.sh          # show current value
```

Or just write to the file yourself:
```
echo 3 > /tmp/uma-hook.ctrl
```

## Windows setup (untested, see warning above)

The Windows side of this repo ships as a single `uma_speed_trainer.exe`
that has the speedhack DLL embedded inside it. Workflow:

1. Grab the prebuilt EXE from the latest run on the
   [Actions tab](../../actions), under "Artifacts".
2. Start Umamusume: Pretty Derby through Steam.
3. Run `uma_speed_trainer.exe`.
4. Click **Inject into game**, then use the ON / OFF buttons.

Or build it yourself with mingw. See [windows/README.md](windows/README.md)
for the gory details, fallback CLI injector (`inject.py`), the .bat
control script, and the DLL source.

Reminder: I, Claude, wrote all of that without ever running it on
Windows. Adjust your expectations.

## What the trainer actually scales

The trainer only scales the clocks Unity uses for `Time.deltaTime` and
similar engine timing. It does not scale wall clock time, so the server
still sees real time when it asks for it, and TLS certificates still
validate.

Linux scales `CLOCK_MONOTONIC_RAW` only. Touching `CLOCK_MONOTONIC`
would break Wine's internal synchronization, because Wine uses absolute
deadlines on that clock and the kernel does not see the scaling. The
clock would say the deadline is in the past, the kernel would say it is
in the future, and the game freezes.

Windows scales `QueryPerformanceCounter`, `GetTickCount`,
`GetTickCount64`, and `timeGetTime` in every module that imports them
through the standard import tables.

## Anti cheat note

Uma Musume relies mostly on server side checks. This does not modify
the wall clock, so the obvious "client time is far from server time"
check does not fire. There is still some risk on your main account.

## Files

```
libuma_hook.c        the Linux LD_PRELOAD source
Makefile             build script for the Linux .so
exports.map          (unused, kept for reference)
launch.sh            Steam launch wrapper
setspeed.sh          CLI speed control
watch.sh             tails the log file
gui.py               PyQt6 ON/OFF window
umagui               tiny shell wrapper that launches gui.py
uma-hook.desktop     KDE app menu entry for the GUI
windows/             Windows port (DLL, injector, bat script, README)
```

## License

MIT. See LICENSE.
