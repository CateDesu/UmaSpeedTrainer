"""Check the built executable without a real game or user state."""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time


artifact = Path(sys.argv[1]).resolve()
repo = Path(__file__).resolve().parents[1]
if os.geteuid() == 0:
    sys.exit("Run package tests as an ordinary user so permission checks are meaningful")

with tempfile.TemporaryDirectory(prefix="uma-package-test-") as temp:
    root = Path(temp)
    program = root / "read only ' program $; folder" / artifact.name
    program.parent.mkdir()
    shutil.copy2(artifact, program)
    program.chmod(0o555)
    program.parent.chmod(0o555)
    scratch = root / "scratch"
    scratch.mkdir()
    env = {"HOME": str(root), "TMPDIR": str(scratch), "PATH": "/usr/bin:/bin",
           "LANG": "C.UTF-8",
           "UMA_HOOK_CTRL": str(root / "ctrl"), "UMA_HOOK_LOG": str(root / "log"),
           "UMA_HOOK_QUIET": "1"}

    def run(*args, **kwargs):
        return subprocess.run([str(program), *args], env=env, text=True,
                              capture_output=True, timeout=40, cwd=root, **kwargs)

    try:
        options = run("--steam-options")
        assert options.returncode == 0, options.stderr
        assert shlex.split(options.stdout) == [str(program), "--steam-launch", "%command%"]
        shell_launch = options.stdout.strip().replace("%command%", "/bin/true")
        quoted = subprocess.run(["/bin/bash", "-c", shell_launch], env=env,
                                capture_output=True, text=True, timeout=40, cwd=root)
        assert quoted.returncode == 0, quoted.stderr
        assert run("--help").returncode == 0
        assert run("--steam-launch").returncode != 0
        assert run("--unknown").returncode != 0
        assert run("--steam-launch", "/bin/bash", "-c", "exit 23").returncode == 23

        probe = root / "probe.py"
        probe.write_text("""import ctypes, json, os, pathlib, sys, time
hook = os.environ['LD_PRELOAD'].split(':')[-1]
assert pathlib.Path(hook).is_file()
assert '_MEI' not in os.environ.get('LD_LIBRARY_PATH', '')
assert not any(k.startswith('_PYI_') for k in os.environ)
assert '_MEI' not in os.environ.get('QT_PLUGIN_PATH', '')
assert float(pathlib.Path(os.environ['UMA_HOOK_CTRL']).read_text()) == 1.0
ctypes.CDLL(hook)
print(json.dumps({'args':sys.argv[1:], 'hook':hook,
                  'libpath':os.environ.get('LD_LIBRARY_PATH'),
                  'qtpath':os.environ.get('QT_PLUGIN_PATH'),
                  'qmlpath':os.environ.get('QML2_IMPORT_PATH'),
                  'preload':os.environ['LD_PRELOAD']}))
""")
        env["LD_LIBRARY_PATH"] = "/usr/lib:/lib"
        env["LD_PRELOAD"] = ":::libm.so.6::::"
        env["QT_PLUGIN_PATH"] = "/original/qt"
        env["QML2_IMPORT_PATH"] = "/original/qml"
        args = ["with spaces", "'quote\"", "$HOME; touch NEVER", "", "--option"]
        result = run("--steam-launch", "/usr/bin/python3", str(probe), *args)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        data = json.loads(result.stdout)
        assert data["args"] == args
        assert data["libpath"] == "/usr/lib:/lib"
        assert data["qtpath"] == "/original/qt"
        assert data["qmlpath"] == "/original/qml"
        assert data["preload"].startswith("libm.so.6:")
        assert "cannot be preloaded" not in result.stderr, result.stderr
        assert not Path(data["hook"]).exists(), "Extraction was not cleaned up"
        assert not (root / "NEVER").exists()
        env.pop("LD_PRELOAD")
        env.pop("LD_LIBRARY_PATH")
        env.pop("QT_PLUGIN_PATH")
        env.pop("QML2_IMPORT_PATH")

        victim = root / "keep.txt"
        victim.write_text("do not change")
        for key in ("UMA_HOOK_CTRL", "UMA_HOOK_LOG"):
            path = Path(env[key])
            path.unlink()
            path.symlink_to(victim)
        result = run("--steam-launch", "/bin/true")
        assert result.returncode != 0, "Unsafe runtime links must stop the launcher"
        assert victim.read_text() == "do not change"
        for key in ("UMA_HOOK_CTRL", "UMA_HOOK_LOG"):
            path = Path(env[key])
            assert path.is_symlink()
            path.unlink()
        result = run("--steam-launch", "/bin/true")
        assert result.returncode == 0, result.stderr
        for key in ("UMA_HOOK_CTRL", "UMA_HOOK_LOG"):
            path = Path(env[key])
            assert path.stat().st_mode & 0o777 == 0o600

        clock_probe = root / "clock_probe"
        early_clock = root / "early_clock.so"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-shared", "-fPIC", "-o", str(early_clock),
                        str(repo / "tests/early_clock.c")], check=True)
        subprocess.run(["gcc", "-Wall", "-Wextra", "-o", str(clock_probe),
                        str(repo / "tests/clock_probe.c"), "-Wl,--no-as-needed",
                        str(early_clock), "-lm"], check=True)
        env["UMA_HOOK_FILTER"] = "clock_probe"
        result = run("--steam-launch", str(clock_probe))
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout.strip())
        clock_stress = root / "clock_stress"
        subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-pthread", "-o", str(clock_stress),
                        str(repo / "tests/clock_stress.c")], check=True)
        env["UMA_HOOK_FILTER"] = "clock_stress"
        negative = subprocess.run([str(clock_stress)], env=env, text=True,
                                  capture_output=True, timeout=10, cwd=root)
        assert negative.returncode != 0 and "Expected 5x" in negative.stderr, negative
        result = run("--steam-launch", str(clock_stress))
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout.strip())
        sleep_probe = root / "sleep_probe"
        subprocess.run(["gcc", "-Wall", "-Wextra", "-o", str(sleep_probe),
                        str(repo / "tests/sleep_probe.c"), "-lm"], check=True)
        env["UMA_HOOK_FILTER"] = "sleep_probe"
        result = run("--steam-launch", str(sleep_probe))
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout.strip())
        env["UMA_HOOK_FILTER"] = "clock_probe"
        long_dir = root / ("x" * 120) / ("y" * 120)
        long_dir.mkdir(parents=True, mode=0o700)
        env["UMA_HOOK_CTRL"] = str(long_dir / "ctrl")
        result = run("--steam-launch", str(clock_probe))
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        env["UMA_HOOK_CTRL"] = str(root / "ctrl")

        quoted_state = root / "state ' with spaces"
        quoted_state.mkdir(mode=0o700)
        env["UMA_HOOK_CTRL"] = str(quoted_state / "ctrl")
        result = run("--steam-launch", str(clock_probe))
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        for value in ("3.5", "off", "4junk", "nan", "0" * 64 + "3"):
            result = subprocess.run(["bash", str(repo / "setspeed.sh"), value],
                                    env=env, text=True, capture_output=True, timeout=10, cwd=root)
            assert (result.returncode == 0) == (value in ("3.5", "off", "0" * 64 + "3")), result.stderr
        assert Path(env["UMA_HOOK_CTRL"]).read_text() == "3"
        env["UMA_HOOK_CTRL"] = str(root / "ctrl")

        protected = root / "protected"
        protected.mkdir(mode=0o555)
        try:
            env["UMA_HOOK_CTRL"] = str(protected / "ctrl")
            failed = run("--steam-launch", "/bin/touch", str(root / "ran"))
            assert failed.returncode != 0 and not (root / "ran").exists()
        finally:
            protected.chmod(0o755)
        env["UMA_HOOK_CTRL"] = str(root / "ctrl")
        env["UMA_HOOK_LOG"] = str(root / "missing" / "log")
        failed = run("--steam-launch", "/bin/touch", str(root / "ran"))
        assert failed.returncode != 0 and not (root / "ran").exists()
        env["UMA_HOOK_LOG"] = str(root / "log")
        env.pop("UMA_HOOK_FILTER")

        # An unwritable control target must stop before executing the command.
        env["UMA_HOOK_CTRL"] = str(root / "missing" / "ctrl")
        failed = run("--steam-launch", "/bin/touch", str(root / "ran"))
        assert failed.returncode != 0
        assert not (root / "ran").exists()
        env["UMA_HOOK_CTRL"] = str(root / "ctrl")

        spaced_temp = root / "temporary files"
        spaced_temp.mkdir()
        env["TMPDIR"] = str(spaced_temp)
        failed = run("--steam-launch", "/bin/touch", str(root / "ran"))
        assert failed.returncode != 0 and "whitespace or colons" in failed.stderr
        assert not (root / "ran").exists()
        env["TMPDIR"] = str(scratch)

        # The bundled GUI must stay running without host Python or Qt.
        env["QT_QPA_PLATFORM"] = "xcb" if os.environ.get("DISPLAY") else "offscreen"
        for key in ("DISPLAY", "XAUTHORITY"):
            if key in os.environ:
                env[key] = os.environ[key]
        proc = subprocess.Popen([str(program)], env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, cwd=root)
        try:
            time.sleep(3)
            assert proc.poll() is None, proc.communicate()
            extracted = list(scratch.glob("_MEI*"))
            assert len(extracted) == 1, extracted
            assert extracted[0].stat().st_mode & 0o777 == 0o700
            source_files = ["gui.py", "libuma_hook.c", "launch.sh", "launcher.py", "runtime.py", "runtime_paths.h",
                            "setspeed.sh", "README.md", "packaging/linux_entry.py",
                            "packaging/launch_environment.py", "packaging/build-linux.sh",
                            "tests/clock_stress.c", "tests/sleep_probe.c"]
            with tarfile.open(artifact.with_name("UmaSpeedTrainer-linux-source.tar.gz")) as archive:
                for name in source_files:
                    current = (repo / name).read_bytes()
                    assert (extracted[0] / "source" / name).read_bytes() == current, name
                    assert archive.extractfile("./" + name).read() == current, name
            elfs = [program]
            for file in extracted[0].rglob("*"):
                if file.is_file() and not file.is_symlink():
                    with file.open("rb") as f:
                        if f.read(4) == b"\x7fELF":
                            elfs.append(file)
            for file in elfs:
                versions = subprocess.check_output(["readelf", "--version-info", str(file)],
                                                   text=True)
                for version in re.findall(r"GLIBC_(\d+\.\d+(?:\.\d+)?)", versions):
                    assert tuple(map(int, version.split("."))) <= (2, 31), (file, version)
            print(f"Checked glibc <= 2.31 requirements in {len(elfs)} ELF files")
            unpacked_size = sum(f.stat().st_size for f in extracted[0].rglob("*")
                                if f.is_file() and not f.is_symlink())
            assert unpacked_size < 300_000_000, unpacked_size
            print(f"Extracted runtime uses {unpacked_size // (1024 * 1024)} MiB")
        finally:
            proc.terminate()
            proc.communicate(timeout=15)
            assert not list(scratch.glob("_MEI*")), "GUI extraction was not cleaned up"
    finally:
        program.parent.chmod(0o755)

print("Portable executable, Steam arguments, environment, cleanup and GUI smoke passed")
