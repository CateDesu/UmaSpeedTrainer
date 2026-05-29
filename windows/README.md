# Windows port (untested)

Same idea as the Linux version but for native Windows. A DLL hooks
`QueryPerformanceCounter`, `GetTickCount`, `GetTickCount64`, and
`timeGetTime` by patching the Import Address Table of every loaded
module that imports them.

Same control file model: write a positive float to `%TEMP%\uma-hook.ctrl`
and the DLL picks it up within 100 milliseconds.

## Build

Cross compile from Linux:

```
sudo pacman -S mingw-w64-gcc        # CachyOS / Arch
sudo apt install gcc-mingw-w64      # Debian / Ubuntu
make
```

Or build on Windows with MSYS2 by installing the `mingw-w64-x86_64-toolchain`
package group, opening the "MINGW64" shell, and running `make`.

You get `uma_hook.dll`.

## Inject

Start the game first, then from a Windows command prompt:

```
python inject.py UmamusumePrettyDerby.exe C:\path\to\uma_hook.dll
```

If you would rather use a GUI injector, Process Hacker, Cheat Engine,
and Extreme Injector all work for this kind of plain LoadLibrary based
DLL.

## Control speed

From a command prompt while the game is running:

```
setspeed.bat 3        # 3x
setspeed.bat 0.5      # half speed
setspeed.bat off      # back to normal
setspeed.bat          # show current value
```

Or just edit `%TEMP%\uma-hook.ctrl` in any text editor.

## What does not work

I could not test any of this against real Windows. Likely failure modes:

* The game may use a clock the DLL does not hook. Unity normally uses
  `QueryPerformanceCounter` so it should be covered, but a different
  game would need different hooks.
* Some anti cheat systems detect IAT modification. Uma Musume on
  Windows ships with anti cheat. The Linux version slips past because
  Wine fsync is the layer that gets confused, not the game itself.
  On real Windows the anti cheat sees the patched IAT directly.
* Modules loaded after the DLL gets injected will not have their IAT
  patched. A re injection or a reload would be needed.

If you actually try this and it works (or breaks in an interesting way),
open an issue.
