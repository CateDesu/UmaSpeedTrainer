# UmaSpeedTrainer

[Discord](https://discord.com/invite/TQJrbZcgKF)

A 100% vibeslopped-by-Claude speed trainer for **Umamusume: Pretty Derby**. Lets you fast forward
through the slow parts of training, races, and menus with a Set/Off
button.

* Linux (Proton): works. Tested up to 5x with no freezes, no crashes.
* Windows: **UNTESTED. USE AT YOUR OWN RISK.** See the box below.

## Linux download and setup

1. Download **[UmaSpeedTrainer-linux-x86_64](https://github.com/CateDesu/UmaSpeedTrainer/releases/latest/download/UmaSpeedTrainer-linux-x86_64)**
   from the [latest release](https://github.com/CateDesu/UmaSpeedTrainer/releases/latest).
   Keep it somewhere permanent, such as `~/Applications/`.
2. Allow it to run, then open it:

   ```sh
   chmod +x ~/Applications/UmaSpeedTrainer-linux-x86_64
   ~/Applications/UmaSpeedTrainer-linux-x86_64
   ```

   You can also use your file manager's executable permission setting and
   double click the file. This is a portable executable with Python, PyQt6,
   Qt and the 64-bit hook bundled. No cloning, compiler, pip, installer,
   root access or FUSE is needed.
3. Print the Steam setup line:

   ```sh
   ~/Applications/UmaSpeedTrainer-linux-x86_64 --steam-options
   ```

   Copy its entire output into **Steam → Umamusume: Pretty Derby →
   Properties → General → Launch Options**. For example:

   ```text
   /home/yourname/Applications/UmaSpeedTrainer-linux-x86_64 --steam-launch %command%
   ```

   Use the generated line if your path contains spaces or quotes. Do not
   replace `%command%` with the game's EXE. The wrapper must start Steam's
   Proton command. Launch the game through Steam as usual, then open the
   same downloaded executable to use **Set** and **OFF**. Each game launch
   resets speed to 1.0. The GUI does not start the game or edit Steam.

### Supported Linux systems and limits

The executable targets **x86_64 glibc Linux, glibc 2.31 or newer**, built on
Debian 11 with a generic x86_64 compiler target. This covers the ABI baseline
of Debian 11+, Ubuntu 20.04+, current Arch Linux and current Fedora.
Distribution coverage is based on that ABI requirement, not game testing
on every distribution. ARM, 32-bit Linux, Alpine/musl and NixOS are not
supported by this download.

A graphical desktop with X11 or XWayland, system OpenGL/EGL libraries,
fonts and graphics drivers is still required. The bundled Qt includes its
X11 dependencies; Python and Qt need not be installed on the host. On a
minimal desktop, the graphics runtime packages are:

```sh
# Debian or Ubuntu
sudo apt install libgl1 libegl1
# Arch
sudo pacman -S libglvnd
# Fedora
sudo dnf install libglvnd-glx libglvnd-egl
```

The source shell scripts need Bash and Python 3. Both Python and the launch
wrapper are bundled in the downloadable executable.

Use the native Steam Linux client and a 64-bit Proton game. Flatpak/Snap
Steam and other sandboxes are not supported by this package. It includes
only the 64-bit hook; 32-bit Wine helper processes may report a harmless
wrong ELF class warning. Actual game and Proton version compatibility
still needs testing with the downloaded build. The GUI uses X11, through
XWayland on Wayland desktops. Native Wayland plugins are not bundled.
Always-on-top behavior depends on the window manager.

The executable unpacks into a private temporary directory on every run.
The temporary filesystem must allow execution and symbolic links, with
at least 300 MB free for the bundled runtime per running instance. `TMPDIR`
can select another directory. For Steam
launching it must have no whitespace or colons, because `LD_PRELOAD` cannot
quote them. The executable's own path can contain spaces. Keep the binary
and its temporary files available while the game runs.

The control file and log live in `$XDG_RUNTIME_DIR/uma-hook` when
`XDG_RUNTIME_DIR` is set, or `/tmp/uma-hook-<uid>` otherwise. The directory
must belong to you with mode `0700`. Files use mode `0600`.

`UMA_HOOK_CTRL` and `UMA_HOOK_LOG` can override the file paths. Their
parent directories must also belong to you with mode `0700`. Existing
files must be owned regular files with mode `0600` and no extra hard
links. Symbolic links in file paths are rejected. Unsafe paths stop the
launcher and controls without overwriting their targets. The hook ignores
unsafe control files and disables logging when the log path is unsafe.

Use `./watch.sh` to follow the log. It keeps the validated file open, so
restart it if you delete and recreate the log.

**OFF** writes 1.0; closing the GUI leaves the selected speed active.

There is no installer or automatic updater. To update, close the game and
GUI, replace the executable at the same path and allow execution again.
If you move or rename it, regenerate the Steam launch line. To remove it,
clear the Steam Launch Options and delete the executable.

### Building from source

For development, install GCC, Make, Python 3 and PyQt6 using your
Linux package manager, then run:

```sh
make
python3 gui.py
```

Use the quoted absolute path to `launch.sh` in Steam, followed by
`%command%`. The source directory itself must have no whitespace or colons
because its hook is loaded directly. The optional `make all32` needs the
32-bit compiler and C development libraries. `make install` also adds an
app menu entry for a source checkout; it does not install the portable
executable.

The source tools remain available:

```sh
./setspeed.sh 3        # 3x
./setspeed.sh off      # normal speed
./setspeed.sh          # current value
./watch.sh            # hook log
```

### Building the downloadable executable

On an x86_64 Linux machine with Docker:

```sh
docker build -f packaging/Dockerfile.linux -t uma-linux .
mkdir -p dist
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/src" uma-linux
```

Podman can use the same Dockerfile. The output is
`dist/UmaSpeedTrainer-linux-x86_64`, with matching build inputs in
`dist/UmaSpeedTrainer-linux-source.tar.gz`. The pinned Debian 11 image and Python
requirements preserve the glibc baseline. Debian packages come from its
archive. The recipe rebuilds the package from source; it does not promise
byte-for-byte identical output across different build dates.

The build tests Steam argument forwarding, resource lifetime, temporary
extraction, library environment isolation, the glibc requirements of every
bundled ELF file, clock and sleep behavior and GUI controls under Xvfb.
The clock stress check also runs without the hook and must fail, so a
missing hook cannot pass that test. Package checks require an ordinary
user to exercise permission failures. These checks
use temporary state and do not launch the game or Steam. GitHub Actions
builds the same executable on pushes and pull requests, and attaches it to
`v*` tag releases alongside the existing Windows files. Workflow artifacts
are ZIP files; extract them and restore the executable permission.

See [Linux bundle notices](packaging/THIRD_PARTY.md) for dependency licenses
and source locations. The trainer's own source stays MIT licensed; the
Linux bundle includes GPLv3 PyQt6 and LGPLv3 Qt.

## Windows setup (untested)

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

The Windows side of this repo ships as a single `uma_speed_trainer.exe`
that has the speedhack DLL embedded inside it. Workflow:

1. Download `uma_speed_trainer.exe` from the
   [latest release](../../releases/latest).
2. Start Umamusume: Pretty Derby through Steam.
3. Run `uma_speed_trainer.exe`.
4. Click **Inject into game**, then use the **Set** / **OFF** buttons.

Or build it yourself with mingw. See [windows/README.md](windows/README.md)
for the gory details, fallback CLI injector (`inject.py`), the .bat
control script, and the DLL source.

Reminder: I, Claude, wrote all of that without ever running it on
Windows. Adjust your expectations.

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

Relative sleep requests are divided by the speed. Interrupted sleeps
return the remaining duration in the caller's scaled time. Absolute
sleep deadlines stay unchanged. A scaled sleep too large to represent
returns `EOVERFLOW`.

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
runtime.py           private runtime files shared by the Linux controls
runtime_paths.h      private runtime files for the Linux hook
launcher.py          shared source and portable launch wrapper
watch.sh             tails the log file
gui.py               PyQt6 Set/OFF window
umagui               tiny shell wrapper that launches gui.py
uma-hook.desktop.in  template for the app menu entry (make install fills in the path)
packaging/           portable Linux executable build and dependency notices
tests/               isolated Linux package and GUI checks
windows/             Windows port (DLL, injector, bat script, README)
```

## License

MIT. See LICENSE.
