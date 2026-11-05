import os
import fcntl
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runtime


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.probe = str(Path(cls.build.name) / "runtime-probe")
        subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                        str(ROOT / "tests/runtime_probe.c"), "-o", cls.probe], check=True)
        subprocess.run(["make", "all"], cwd=ROOT, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = {key: value for key, value in os.environ.items()
                    if key not in ("UMA_HOOK_CTRL", "UMA_HOOK_LOG", "LD_PRELOAD")}
        self.env["XDG_RUNTIME_DIR"] = str(self.base)
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def probe_run(self, command, path, *args):
        return subprocess.run([self.probe, command, str(path), *map(str, args)],
                              env=os.environ, capture_output=True, text=True, timeout=3)

    def file(self, path, value="unchanged"):
        path.write_text(value)
        path.chmod(0o600)
        return path

    def test_defaults_match_c_and_are_private(self):
        for kind, leaf in (("ctrl", "control"), ("log", "hook.log")):
            expected = self.base / "uma-hook" / leaf
            self.assertEqual(runtime.runtime_path(kind), str(expected))
            result = self.probe_run("path", kind)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(expected))
        runtime.write_speed(3)
        self.assertEqual(runtime.read_speed(), 3)
        self.assertEqual(stat.S_IMODE((self.base / "uma-hook").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.base / "uma-hook/control").stat().st_mode), 0o600)

    def test_private_overrides_and_shell_controls(self):
        path = self.base / "custom-control"
        os.environ["UMA_HOOK_CTRL"] = str(path)
        result = subprocess.run([str(ROOT / "setspeed.sh"), "2.5"], env=os.environ,
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_text(), "2.5")
        self.assertEqual(self.probe_run("read", path).stdout, "2.5")
        self.assertEqual(self.probe_run("write", path).returncode, 0)
        self.assertEqual(runtime.read_speed(), 3)

    def test_unsafe_leaf_types_never_overwrite_target_or_block(self):
        target = self.file(self.base / "target")
        for kind in ("symlink", "hardlink", "fifo", "directory", "public-file"):
            with self.subTest(kind=kind):
                path = self.base / kind
                if kind == "symlink":
                    path.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, path)
                elif kind == "fifo":
                    os.mkfifo(path, 0o600)
                elif kind == "directory":
                    path.mkdir(mode=0o700)
                else:
                    self.file(path).chmod(0o644)
                with self.assertRaises(OSError):
                    with runtime.open_runtime(path, os.O_WRONLY | os.O_CREAT):
                        self.fail("unsafe file accepted")
                with self.assertRaises(OSError):
                    with runtime.open_runtime(path, os.O_RDONLY):
                        self.fail("unsafe file accepted")
                for command in ("read", "write"):
                    self.assertNotEqual(self.probe_run(command, path).returncode, 0)
                self.assertEqual(target.read_text(), "unchanged")
                if kind == "directory":
                    path.rmdir()
                else:
                    path.unlink()

    def test_unsafe_runtime_directory_is_rejected(self):
        for kind in ("symlink", "public"):
            with self.subTest(kind=kind):
                directory = self.base / "uma-hook"
                if kind == "symlink":
                    directory.symlink_to(self.base, target_is_directory=True)
                else:
                    directory.mkdir(mode=0o755)
                with self.assertRaises(OSError):
                    runtime.runtime_path("ctrl")
                self.assertNotEqual(self.probe_run("path", "ctrl").returncode, 0)
                if kind == "symlink":
                    directory.unlink()
                else:
                    directory.rmdir()

    def test_symlink_ancestor_and_shared_parent_are_rejected(self):
        private = self.base / "private"
        private.mkdir(mode=0o700)
        link = self.base / "link"
        link.symlink_to(private, target_is_directory=True)
        shared = self.base / "shared"
        shared.mkdir(mode=0o777)
        shared.chmod(0o777)
        for path in (link / "control", shared / "control"):
            with self.subTest(path=path):
                with self.assertRaises(OSError):
                    with runtime.open_runtime(path, os.O_WRONLY | os.O_CREAT):
                        self.fail("unsafe parent accepted")
                self.assertNotEqual(self.probe_run("write", path).returncode, 0)
                self.assertFalse(path.exists())

    def test_symlink_swap_at_open_is_rejected(self):
        path = self.file(self.base / "control", "1")
        target = self.file(self.base / "target")
        actual_open = os.open

        def replace_before_open(name, flags, *args, **kwargs):
            if name == path.name:
                path.unlink()
                path.symlink_to(target)
            return actual_open(name, flags, *args, **kwargs)

        os.environ["UMA_HOOK_CTRL"] = str(path)
        with patch.object(os, "open", side_effect=replace_before_open):
            with self.assertRaises(OSError):
                runtime.write_speed(3)
        self.assertEqual(target.read_text(), "unchanged")

    def test_private_parent_below_writable_ancestor_is_rejected(self):
        for mode in (0o770, 0o777):
            with self.subTest(mode=oct(mode)):
                shared = self.base / f"shared-{mode}"
                shared.mkdir(mode=mode)
                shared.chmod(mode)
                parent = shared / "expected"
                parent.mkdir(mode=0o700)
                alternate = shared / "alternate"
                alternate.mkdir(mode=0o700)
                self.file(parent / "control", "1")
                self.file(alternate / "control", "sentinel")
                parent.rename(shared / "original")
                alternate.rename(parent)
                os.environ["UMA_HOOK_CTRL"] = str(parent / "control")
                with self.assertRaises(PermissionError):
                    runtime.write_speed(3)
                self.assertNotEqual(self.probe_run("write", parent / "control").returncode, 0)
                self.assertEqual((parent / "control").read_text(), "sentinel")
                self.assertEqual((shared / "original/control").read_text(), "1")

    def test_foreign_ancestor_is_rejected(self):
        actual_fstat = os.fstat
        shared = self.base / "foreign"
        shared.mkdir(mode=0o755)
        parent = shared / "private"
        parent.mkdir(mode=0o700)
        shared_inode = shared.stat().st_ino

        def foreign_owner(fd):
            info = actual_fstat(fd)
            if info.st_ino == shared_inode:
                values = list(info)
                values[4] = os.geteuid() + 1
                return os.stat_result(values)
            return info

        with patch.object(os, "fstat", side_effect=foreign_owner):
            with self.assertRaises(PermissionError):
                with runtime.open_runtime(parent / "control", os.O_WRONLY | os.O_CREAT):
                    self.fail("foreign ancestor accepted")
        self.assertFalse((parent / "control").exists())

    def test_path_swap_after_open_keeps_original_descriptor(self):
        path = self.file(self.base / "control", "1")
        target = self.file(self.base / "target")
        original = self.base / "original"
        actual_ftruncate = os.ftruncate

        def replace_after_open(fd, length):
            path.rename(original)
            path.symlink_to(target)
            return actual_ftruncate(fd, length)

        os.environ["UMA_HOOK_CTRL"] = str(path)
        with patch.object(os, "ftruncate", side_effect=replace_after_open):
            runtime.write_speed(3)
        self.assertEqual(original.read_text(), "3")
        self.assertEqual(target.read_text(), "unchanged")

    def test_parent_swap_keeps_validated_directory(self):
        for implementation in ("python", "c"):
            with self.subTest(implementation=implementation):
                parent = self.base / implementation
                parent.mkdir(mode=0o700)
                attack = self.base / f"{implementation}-attack"
                attack.mkdir(mode=0o700)
                target = self.file(attack / "control")
                moved = self.base / f"{implementation}-moved"
                path = parent / "control"
                if implementation == "c":
                    result = self.probe_run("parent-race", path, moved, attack)
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    actual_open = os.open

                    def replace_parent(name, flags, *args, **kwargs):
                        if name == "control":
                            parent.rename(moved)
                            parent.symlink_to(attack, target_is_directory=True)
                        return actual_open(name, flags, *args, **kwargs)

                    os.environ["UMA_HOOK_CTRL"] = str(path)
                    with patch.object(os, "open", side_effect=replace_parent):
                        runtime.write_speed(3)
                self.assertEqual(target.read_text(), "unchanged")
                self.assertEqual((moved / "control").read_text(), "3")

    def test_invalid_speeds_are_rejected(self):
        for value in ("nan", "inf", "-1", "0", "1001", "2junk"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    runtime.write_speed(value)

    def test_reader_rejects_truncated_and_nondecimal_values(self):
        path = Path(runtime.runtime_path("ctrl"))
        for value in (b"3" + b" " * 64, b"1_0", b"3\x00junk", b"\xff"):
            with self.subTest(value=value):
                path.write_bytes(value)
                path.chmod(0o600)
                with self.assertRaises(ValueError):
                    runtime.read_speed()

    def test_reader_does_not_wait_for_a_writer(self):
        runtime.write_speed(3)
        path = runtime.runtime_path("ctrl")
        with runtime.open_runtime(path, os.O_WRONLY) as fd:
            fcntl.flock(fd, fcntl.LOCK_EX)
            result = subprocess.run([sys.executable, str(ROOT / "runtime.py"), "speed"],
                                    env=os.environ, capture_output=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)

    def test_concurrent_writers_cannot_merge_control_values(self):
        runtime.write_speed(5)
        first_paused = threading.Event()
        release_first = threading.Event()
        second_finished = threading.Event()
        errors = []
        actual_truncate = os.ftruncate

        def pause_first(fd, length):
            actual_truncate(fd, length)
            if threading.current_thread().name == "first-control-writer":
                first_paused.set()
                if not release_first.wait(3):
                    raise TimeoutError("first writer was not released")

        def write(value, finished=None):
            try:
                runtime.write_speed(value)
            except BaseException as error:
                errors.append(error)
            finally:
                if finished is not None:
                    finished.set()

        with patch.object(os, "ftruncate", side_effect=pause_first):
            first = threading.Thread(target=write, args=(1000,), name="first-control-writer")
            second = threading.Thread(target=write, args=(1, second_finished))
            first.start()
            self.assertTrue(first_paused.wait(1))
            second.start()
            try:
                self.assertFalse(second_finished.wait(0.1))
            finally:
                release_first.set()
                first.join(3)
                second.join(3)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(runtime.read_speed(), 1)

    def test_hook_uses_controls_and_rejects_unsafe_log(self):
        runtime.write_speed(3)
        log = Path(runtime.runtime_path("log"))
        env = dict(os.environ, LD_PRELOAD=str(ROOT / "lib64/libuma_hook.so"))
        result = subprocess.run(["/bin/true"], env=env, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertIn("speed=3", log.read_text())
        log.unlink()
        target = self.file(self.base / "target")
        log.symlink_to(target)
        result = subprocess.run(["/bin/true"], env=env, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "unchanged")

    def test_hook_ignores_unsafe_or_invalid_controls_without_blocking(self):
        control = Path(runtime.runtime_path("ctrl"))
        log = Path(runtime.runtime_path("log"))
        target = self.file(self.base / "target", "3")
        env = dict(os.environ, LD_PRELOAD=str(ROOT / "lib64/libuma_hook.so"))
        for kind in ("symlink", "fifo", "nan", "inf", "2junk"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    control.symlink_to(target)
                elif kind == "fifo":
                    os.mkfifo(control, 0o600)
                else:
                    self.file(control, kind)
                result = subprocess.run(["/bin/true"], env=env, capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 0)
                self.assertIn("speed=1", log.read_text())
                self.assertNotIn("speed=3", log.read_text())
                control.unlink()
                log.unlink()

    def test_launcher_resets_speed_and_creates_private_log(self):
        runtime.write_speed(5)
        result = subprocess.run([str(ROOT / "launch.sh"), "/bin/echo", "started"],
                                env=os.environ, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "started")
        self.assertEqual(runtime.read_speed(), 1)
        log = Path(runtime.runtime_path("log"))
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        self.assertIn("[launch.sh]", log.read_text())

    def test_launcher_refuses_unsafe_paths_before_starting_command(self):
        target = self.file(self.base / "target")
        control = self.base / "control"
        control.symlink_to(target)
        env = dict(os.environ, UMA_HOOK_CTRL=str(control))
        result = subprocess.run([str(ROOT / "launch.sh"), "/bin/echo", "started"],
                                env=env, capture_output=True, text=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("started", result.stdout)
        self.assertEqual(target.read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
