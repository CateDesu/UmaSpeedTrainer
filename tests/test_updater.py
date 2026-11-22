"""Exercise portable updates without contacting GitHub."""

from contextlib import ExitStack
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.program = self.root / "trainer's portable copy"
        self.original = b"original executable"
        self.program.write_bytes(self.original)
        self.program.chmod(0o750)
        self.running = self.root / "running"
        os.link(self.program, self.running)
        stack.enter_context(patch.object(updater, "RUNNING_PROGRAM", self.running))
        self.open = stack.enter_context(patch.object(updater, "_open"))
        self.download = b"\x7fELF\x02\x01\x01" + bytes(11) + b"\x3e\x00" + b"new executable"

    def publish(self, content):
        digest = hashlib.sha256(content).hexdigest()
        asset = {"name": updater.ASSET, "size": len(content), "digest": f"sha256:{digest}"}
        self.open.return_value = io.BytesIO(json.dumps({"tag_name": "v2.0.0", "assets": [asset]}).encode())
        return updater.Release("v2.0.0", len(content), digest)

    def test_replaces_executable_at_same_path_and_keeps_running_inode(self):
        release = self.publish(self.download)
        self.assertEqual(updater.check_for_update(self.program), release)
        self.open.assert_called_once_with(f"https://api.github.com/repos/{updater.REPO}/releases/latest",
                                          "application/vnd.github+json")
        self.open.reset_mock()
        self.open.return_value = io.BytesIO(self.download)
        updater.install_update(self.program, release)
        self.open.assert_called_once_with(f"https://github.com/{updater.REPO}/releases/download/"
                                          f"{release.tag}/{updater.ASSET}", "application/octet-stream")
        self.assertEqual(self.program.read_bytes(), self.download)
        self.assertEqual(self.program.stat().st_mode & 0o777, 0o750)
        self.assertEqual(self.running.read_bytes(), self.original)
        self.assertFalse(list(self.root.glob(".uma-update-*")))

    def test_latest_executable_needs_no_update(self):
        self.program.write_bytes(self.download)
        self.publish(self.download)
        self.assertIsNone(updater.check_for_update(self.program))

    def test_release_unavailable(self):
        self.open.return_value = io.BytesIO(b'{"tag_name":"v2.0.0","assets":[]}')
        with self.assertRaisesRegex(updater.UpdateError, "no portable Linux download"):
            updater.check_for_update(self.program)
        self.open.side_effect = HTTPError("", 404, "Not Found", None, None)
        with self.assertRaisesRegex(updater.UpdateError, "No official release"):
            updater.check_for_update(self.program)

    def test_invalid_download_never_replaces_executable(self):
        release = self.publish(self.download)
        for content in (self.download[:-1], self.download + b"extra", self.download[:-1] + b"x"):
            with self.subTest(content=content):
                self.open.return_value = io.BytesIO(content)
                with self.assertRaises(updater.UpdateError):
                    updater.install_update(self.program, release)
                self.assertTrue(self.program.samefile(self.running))
                self.assertFalse(list(self.root.glob(".uma-update-*")))

    def test_running_instance_cannot_overwrite_replacement(self):
        replacement = self.root / "replacement"
        replacement.write_bytes(self.download)
        replacement.replace(self.program)
        with self.assertRaisesRegex(updater.UpdateError, "changed on disk"):
            updater.install_update(self.program, self.publish(self.download))
        self.open.assert_not_called()
        self.assertEqual(self.program.read_bytes(), self.download)

    def test_parallel_update_fails_before_download(self):
        with self.running.open("rb") as locked:
            fcntl.flock(locked, fcntl.LOCK_EX)
            with self.assertRaisesRegex(updater.UpdateError, "Another trainer window"):
                updater.install_update(self.program, self.publish(self.download))
        self.open.assert_not_called()
