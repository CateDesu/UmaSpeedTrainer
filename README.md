# UmaSpeedTrainer

Join the [Discord](https://discord.com/invite/TQJrbZcgKF) if you need help or something.

A surprising amount of people are seemingly using this.\
I added an update function and cleaned up the README :)

Speed up **Umamusume: Pretty Derby**. Choose a speed from 1× to 5× and press **Set**. Press **OFF** to return to normal. Using a trainer may put your game account at risk.

## Linux setup

Use native Steam with Proton. Flatpak and Snap Steam are unsupported.

- **[Download for Linux](https://github.com/CateDesu/UmaSpeedTrainer/releases/latest/download/UmaSpeedTrainer-linux-x86_64)** and save the file in `~/Applications/`.

  ```sh
  chmod +x ~/Applications/UmaSpeedTrainer-linux-x86_64
  ~/Applications/UmaSpeedTrainer-linux-x86_64 --steam-options
  ```
- **Git clone.** Install GCC, Make, Python 3 and PyQt6. Run `make install` from the clone. Use a folder without spaces or colons.

Paste the printed command into the game’s **Properties → General → Launch Options**. If you already use a wrapper, replace just `%command%` with the printed command.

**Portable download**

```sh
"$HOME/Applications/UmaSpeedTrainer-linux-x86_64" --steam-launch %command%
```

**Source install** (example clone in `~/Projects/UmaSpeedTrainer`)

```sh
"$HOME/Projects/UmaSpeedTrainer/launch.sh" %command%
```

Launch the game through Steam, then open the downloaded trainer or **Uma Hook** from your app menu. Closing the trainer leaves the speed active. Relaunching the game resets it to 1×.

**Update** checks official releases for the download or the upstream branch for a clone. Reopen the trainer after installing. If you move the trainer, update its path in Steam. Before uninstalling, restore your previous launch options.

### If Set has no effect

Steam may need access to the trainer’s control folder. Add the folder setting at the start of your launch command.

**Portable download**

```sh
PRESSURE_VESSEL_FILESYSTEMS_RW="$XDG_RUNTIME_DIR/uma-hook" "$HOME/Applications/UmaSpeedTrainer-linux-x86_64" --steam-launch %command%
```

**Source install**

```sh
PRESSURE_VESSEL_FILESYSTEMS_RW="$XDG_RUNTIME_DIR/uma-hook" "$HOME/Projects/UmaSpeedTrainer/launch.sh" %command%
```

If that option already exists, append the folder to its list with a colon. If `XDG_RUNTIME_DIR` is unset, use `/tmp/uma-hook-$(id -u)`. For custom `UMA_HOOK_CTRL` or `UMA_HOOK_LOG` paths, share their parent folders. Restart the game and press **Set** again.

## Windows

The Windows build is **untested**. [Windows setup](windows/README.md)

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

[MIT license](LICENSE) · [Linux bundle licenses](packaging/THIRD_PARTY.md)
