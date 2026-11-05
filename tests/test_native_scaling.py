import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runtime


class NativeScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.probe = str(Path(cls.build.name) / "native-scaling-probe")
        subprocess.run(["gcc", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined,float-cast-overflow", "-fno-sanitize-recover=all",
                        str(ROOT / "tests/native_scaling_probe.c"), "-o", cls.probe,
                        "-ldl", "-lpthread", "-lrt"], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.control = self.directory / "control"
        self.control.touch(mode=0o600)
        self.env = dict(os.environ, UMA_HOOK_CTRL=str(self.control),
                        UMA_HOOK_LOG=str(self.directory / "hook.log"),
                        UMA_HOOK_FILTER="", UMA_SPEED="1")
        self.env.pop("LD_PRELOAD", None)

    def probe_run(self, mode, speed="1"):
        self.control.write_text(speed)
        result = subprocess.run([self.probe, mode], env=self.env, capture_output=True,
                                text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout.strip()

    def test_supported_speeds_and_extreme_delays_are_representable(self):
        for speed in ("1", "0.5", "2", "1000", "1e-300"):
            expected = 1_000_000 / float(speed)
            for method in ("nanosleep", "usleep", "clock-relative"):
                with self.subTest(speed=speed, method=method):
                    output = self.probe_run(method, speed)
                    if speed == "1e-300":
                        self.assertEqual(output, "overflow")
                        continue
                    seconds, nanos = map(int, output.split())
                    self.assertEqual(seconds * 1_000_000_000 + nanos, int(expected))
                    self.assertTrue(0 <= nanos < 1_000_000_000)

    def test_large_native_inputs_do_not_overflow_clock_math(self):
        for mode in ("large-delay", "clock-absolute", "clock-scale", "add-upper", "add-lower"):
            with self.subTest(mode=mode):
                _, nanos = map(int, self.probe_run(mode, "1000").split())
                self.assertTrue(0 <= nanos < 1_000_000_000)

    def test_positive_subnanosecond_delay_rounds_up(self):
        self.assertEqual(self.probe_run("tiny-delay", "1000"), "0 1")

    def test_native_control_reader_does_not_block_on_writer(self):
        self.control.write_text("3")
        with runtime.open_runtime(self.control, os.O_WRONLY) as fd:
            fcntl.flock(fd, fcntl.LOCK_EX)
            result = subprocess.run([self.probe, "read"], env=self.env, capture_output=True,
                                    text=True, timeout=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "read=0")


if __name__ == "__main__":
    unittest.main()
