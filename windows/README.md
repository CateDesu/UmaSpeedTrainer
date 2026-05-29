# Windows port

> [!WARNING]
> ### UNTESTED. USE AT YOUR OWN RISK.
>
> I am Claude, an AI assistant. I wrote every file in this folder
> without ever running it on Windows. There is no version of "I tried
> it on my machine" that applies here, because I do not have a machine.
> The logic is translated from the Linux build that does work, but
> translations have bugs, anti cheat has opinions, and Windows is its
> own weather system.
>
> Treat the contents of this folder as a starting point, not a release.

A single GUI EXE that carries the speedhack DLL inside it. When you
click "Inject into game" the EXE writes the DLL to `%TEMP%`, finds
the running game, and injects it. After that, the ON, OFF, and speed
picker just write to the same control file the DLL polls.

## Get the EXE

GitHub Actions builds `uma_speed_trainer.exe` on every push to `main`.
Download the latest artifact from the
[Actions tab](../../actions) of the repo and unzip it.

If you would rather build it yourself, see [Build](#build) below.

## Use

1. Start Umamusume: Pretty Derby normally through Steam.
2. Run `uma_speed_trainer.exe`.
3. Click **Inject into game**.
4. Set the speed and click **ON**. Click **OFF** before any loading
   screen or server call.

## Build

Cross compile from Linux:

```
sudo pacman -S mingw-w64-gcc        # CachyOS / Arch
sudo apt install gcc-mingw-w64      # Debian / Ubuntu
cd windows
make
```

On Windows with MSYS2:

```
pacman -S mingw-w64-x86_64-gcc make
cd windows
make CC=gcc WINDRES=windres
```

You get `uma_speed_trainer.exe` and a standalone `uma_hook.dll` next
to it.

## What it hooks

The DLL walks every loaded module in the game and rewrites Import
Address Table entries for these functions:

* `QueryPerformanceCounter` (this is the big one for Unity)
* `GetTickCount`
* `GetTickCount64`
* `timeGetTime`

Modules that get loaded later than the injection time will not be
patched. For Unity that is usually fine because `UnityPlayer.dll`
loads very early.

## Caveats

* Anti cheat may detect the IAT writes. Uma Musume on Windows ships
  with anti cheat. The Linux build slips past because Wine is the
  layer that gets confused, not the game. On real Windows the anti
  cheat sees the patched IAT directly.
* This code has never been run on real Windows by the author.
  Open an issue if it works or breaks.
