# UmaSpeedTrainer

A surprising amount of people are seemingly using this. I added an update function and cleaned up the README slop :)

Speed up **Umamusume: Pretty Derby**. Choose a speed from 1× to 5× and press **Set**. Press **OFF** to return to normal. Using a trainer may put your game account at risk.

## Linux setup

Use native Steam with Proton. Flatpak and Snap Steam are unsupported.

- **Portable download.** Sign in to GitHub, open a successful build, and extract the `UmaSpeedTrainer-linux-x86_64` artifact into `~/Applications/`. [Linux builds](https://github.com/CateDesu/UmaSpeedTrainer/actions/workflows/build.yml)

  ```sh
  chmod +x ~/Applications/UmaSpeedTrainer-linux-x86_64
  ~/Applications/UmaSpeedTrainer-linux-x86_64 --steam-options
  ```
- **Git clone.** Install GCC, Make, Python 3 and PyQt6. Run `make install` from the clone. Use a folder without spaces or colons.

Paste the printed command into the game’s **Properties → General → Launch Options**. If you already use a wrapper like `mullvad-exclude %command%`, replace just `%command%` with the printed command.

Launch the game through Steam, then open the downloaded trainer or **Uma Hook** from your app menu. Closing the trainer leaves the speed active. Relaunching the game resets it to 1×.

**Update** checks official releases for the download or the upstream branch for a clone. Reopen the trainer after installing. If you move the trainer, update its path in Steam. Before uninstalling, restore your previous launch options.

### If Set has no effect

Steam may need access to the trainer’s control folder. Put this before your launch command, including before `mullvad-exclude` if you use it:

```sh
PRESSURE_VESSEL_FILESYSTEMS_RW="$XDG_RUNTIME_DIR/uma-hook"
```

If that option already exists, append the folder to its list with a colon. If `XDG_RUNTIME_DIR` is unset, use `/tmp/uma-hook-$(id -u)`. For custom `UMA_HOOK_CTRL` or `UMA_HOOK_LOG` paths, share their parent folders. Restart the game and press **Set** again.

## Windows

The Windows build is **untested**. [Windows setup](windows/README.md)

[Discord](https://discord.com/invite/TQJrbZcgKF) · [MIT license](LICENSE) · [Linux bundle licenses](packaging/THIRD_PARTY.md)
