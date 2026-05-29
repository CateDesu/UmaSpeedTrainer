# UmaSpeedTrainer

A speed trainer for **Umamusume: Pretty Derby**. Lets you fast forward
through the slow parts of training, races, and menus with an on/off
button.

* Linux (Proton): works. Tested up to 5x with no freezes, no crashes.
* Windows: untested. Code is included but I do not have a Windows box
  to verify it on.

## How it works

The game asks the operating system "what time is it?" many times per
second. Unity uses the answer to decide how far to advance animations,
physics, timers, and so on. If we lie about how much time has passed,
the game runs faster (or slower) without knowing.

We do not touch game memory, do not patch the game files, and do not
attach as a debugger. We only intercept the system time functions in
a library the game loads. The Linux build does this with `LD_PRELOAD`.
The Windows build does it with a DLL that patches the import tables of
the modules already loaded into the game.

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

## Windows setup (untested)

See [windows/README.md](windows/README.md) for the build, inject, and
control instructions.

The short version: build `uma_hook.dll` with mingw or MSYS2, start the
game, and inject the DLL with `inject.py` or any LoadLibrary based
injector like Process Hacker or Cheat Engine. Control the speed by
writing to `%TEMP%\uma-hook.ctrl` or running `setspeed.bat 3`.

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
