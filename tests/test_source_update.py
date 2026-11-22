"""Exercise the clone updater with an isolated upstream and a real hook build."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import updater


@unittest.skipUnless(shutil.which("git"), "Git is required for source updates")
class SourceUpdateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.remote = Path(temp.name) / "upstream"
        self.clone = Path(temp.name) / "clone"
        self.remote.mkdir()
        self.git(self.remote, "init", "-b", "main")
        root = Path(__file__).resolve().parents[1]
        for name in ("Makefile", "libuma_hook.c", "runtime_paths.h", ".gitignore"):
            shutil.copy(root / name, self.remote)
        self.git(self.remote, "add", ".")
        self.commit("Original build")
        self.git(self.remote, "clone", "-q", ".", str(self.clone))
        self.hook = self.clone / "lib64/libuma_hook.so"
        self.hook.parent.mkdir()
        self.hook.write_bytes(b"running hook")
        (self.remote / "README.md").write_text("Incoming change")
        self.git(self.remote, "add", "README.md")
        self.commit("Update instructions")

    def git(self, directory, *args):
        return subprocess.check_output(["git", *args], cwd=directory, text=True).strip()

    def commit(self, message):
        # Tests also run on CI machines without a configured Git identity.
        options = ["-c", "commit.gpgSign=false"]
        for key, fallback in (("user.name", "Fixture"), ("user.email", "fixture@users.noreply.github.com")):
            if subprocess.run(["git", "config", "--get", key], cwd=self.remote,
                              stdout=subprocess.DEVNULL).returncode:
                options.extend(["-c", f"{key}={fallback}"])
        self.git(self.remote, *options, "commit", "-qam", message)

    def test_update_rebuilds_without_disrupting_open_hook(self):
        untracked = self.clone / "notes"
        untracked.write_text("keep")
        update = updater.check_source_update(self.clone)
        with self.hook.open("rb") as running:
            updater.install_source_update(self.clone, update)
            self.assertEqual(running.read(), b"running hook")
        self.assertTrue(self.hook.read_bytes().startswith(b"\x7fELF"))
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.commit)
        self.assertIsNone(updater.check_source_update(self.clone))
        self.assertEqual(untracked.read_text(), "keep")
        self.assertFalse((self.clone / "lib/libuma_hook.so").exists())

    def test_local_changes_after_confirmation_survive(self):
        update = updater.check_source_update(self.clone)
        (self.clone / "Makefile").write_text("local edit")
        with self.assertRaisesRegex(updater.UpdateError, "local changes"):
            updater.install_source_update(self.clone, update)
        self.assertEqual((self.clone / "Makefile").read_text(), "local edit")
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.head)

    def test_shallow_clone_builds_incoming_commit(self):
        shallow = self.clone.parent / "shallow"
        self.git(self.clone.parent, "clone", "--quiet", "--depth=1", self.remote.as_uri(), str(shallow))
        (self.remote / "README.md").write_text("Update shallow clone")
        self.commit("Update shallow clone")
        update = updater.check_source_update(shallow)
        updater.install_source_update(shallow, update)
        self.assertEqual(self.git(shallow, "rev-parse", "HEAD"), update.commit)
        self.assertTrue((shallow / "lib64/libuma_hook.so").read_bytes().startswith(b"\x7fELF"))

    def test_failed_build_keeps_previous_checkout(self):
        (self.remote / "libuma_hook.c").write_text("#error broken")
        self.commit("Unbuildable update")
        update = updater.check_source_update(self.clone)
        with self.assertRaisesRegex(updater.UpdateError, "broken"):
            updater.install_source_update(self.clone, update)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.head)
        self.assertEqual(self.hook.read_bytes(), b"running hook")
        self.assertEqual(self.git(self.clone, "worktree", "list").count("\n"), 0)

    @unittest.skipIf(os.geteuid() == 0, "Directory permissions require a non-root user")
    def test_read_only_hook_directory_keeps_checkout_and_can_retry(self):
        update = updater.check_source_update(self.clone)
        self.hook.parent.chmod(0o555)
        try:
            with self.assertRaises(PermissionError):
                updater.install_source_update(self.clone, update)
            self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.head)
            self.assertEqual(self.hook.read_bytes(), b"running hook")
        finally:
            self.hook.parent.chmod(0o755)
        self.assertEqual(updater.check_source_update(self.clone), update)
        updater.install_source_update(self.clone, update)
        self.assertIsNone(updater.check_source_update(self.clone))

    def test_merge_preserves_colliding_ignored_file(self):
        (self.clone / ".git/info/exclude").write_text("/README.md\n")
        notes = self.clone / "README.md"
        notes.write_text("local notes")
        update = updater.check_source_update(self.clone)
        with self.assertRaisesRegex(updater.UpdateError, "overwritten"):
            updater.install_source_update(self.clone, update)
        self.assertEqual(notes.read_text(), "local notes")
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.head)
        self.assertEqual(self.hook.read_bytes(), b"running hook")
        self.assertEqual(updater.check_source_update(self.clone), update)

    @unittest.skipIf(os.geteuid() == 0, "Directory permissions require a non-root user")
    def test_permission_failure_after_merge_is_recoverable(self):
        update = updater.check_source_update(self.clone)
        run = updater._run

        def make_read_only_after_merge(directory, *args):
            result = run(directory, *args)
            if "send-pack" in args:
                self.hook.parent.chmod(0o555)
            return result

        try:
            with patch.object(updater, "_run", make_read_only_after_merge):
                with self.assertRaises(PermissionError):
                    updater.install_source_update(self.clone, update)
            self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.commit)
            self.assertEqual(self.hook.read_bytes(), b"running hook")
        finally:
            self.hook.parent.chmod(0o755)
        retry = updater.check_source_update(self.clone)
        self.assertEqual(retry, updater.SourceUpdate(update.branch, update.commit, update.commit))
        updater.install_source_update(self.clone, retry)
        self.assertIsNone(updater.check_source_update(self.clone))

    def test_interrupted_publication_rebuilds_both_hooks_on_retry(self):
        companion = self.clone / "lib/libuma_hook.so"
        companion.parent.mkdir()
        companion.write_bytes(b"old companion")
        # Give the companion a fixture recipe so the test also runs without multilib.
        with (self.remote / "Makefile").open("a") as makefile:
            makefile.write("\nlib/libuma_hook.so:\n\tmkdir -p lib\n\tprintf 'new companion' > $@\n")
        self.commit("Build the fixture companion")
        update = updater.check_source_update(self.clone)
        process = subprocess.run(
            [sys.executable, "-c", """
import os
from pathlib import Path
import sys
from unittest.mock import patch
import updater

replace = Path.replace

def interrupt_after_first_hook(source, target):
    replace(source, target)
    os._exit(41)

with patch.object(Path, "replace", interrupt_after_first_hook):
    updater.install_source_update(Path(sys.argv[1]), updater.SourceUpdate(*sys.argv[2:]))
""", str(self.clone), update.branch, update.head, update.commit],
            cwd=Path(updater.__file__).resolve().parent, timeout=30,
            env={**os.environ, "TMPDIR": str(self.clone.parent)},
        )
        self.assertEqual(process.returncode, 41)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.commit)
        self.assertTrue(self.hook.read_bytes().startswith(b"\x7fELF"))
        self.assertEqual(companion.read_bytes(), b"old companion")

        retry = updater.check_source_update(self.clone)
        self.assertEqual(retry, updater.SourceUpdate(update.branch, update.commit, update.commit))
        updater.install_source_update(self.clone, retry)
        self.assertEqual(companion.read_bytes(), b"new companion")
        self.assertFalse((self.clone / ".git/index.lock").exists())
        self.assertIsNone(updater.check_source_update(self.clone))

    def newer_commit(self):
        (self.remote / "README.md").write_text("Newer change")
        self.commit("Newer instructions")
        self.git(self.clone, "fetch", "--quiet")
        return self.git(self.clone, "rev-parse", "origin/main")

    def test_intervening_fast_forward_never_publishes_the_older_hook(self):
        update = updater.check_source_update(self.clone)
        newer = self.newer_commit()
        run = updater._run

        def merge_newer_first(directory, *args):
            if "send-pack" in args:
                self.git(self.clone, "merge", "--ff-only", newer)
            return run(directory, *args)

        with patch.object(updater, "_run", merge_newer_first):
            with self.assertRaises(updater.UpdateError):
                updater.install_source_update(self.clone, update)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), newer)
        self.assertEqual(self.hook.read_bytes(), b"running hook")
        self.assertEqual((self.clone / "README.md").read_text(), "Newer change")
        retry = updater.check_source_update(self.clone)
        self.assertEqual(retry, updater.SourceUpdate(update.branch, newer, newer))
        updater.install_source_update(self.clone, retry)
        self.assertIsNone(updater.check_source_update(self.clone))

    def test_switching_branches_does_not_fast_forward_the_other_branch(self):
        update = updater.check_source_update(self.clone)
        run = updater._run

        def switch_before_advance(directory, *args):
            if "send-pack" in args:
                self.git(self.clone, "switch", "-q", "-c", "other")
            return run(directory, *args)

        with patch.object(updater, "_run", switch_before_advance):
            with self.assertRaises(updater.UpdateError):
                updater.install_source_update(self.clone, update)
        self.assertEqual(self.git(self.clone, "branch", "--show-current"), "other")
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.head)
        self.assertFalse((self.clone / "README.md").exists())
        self.assertEqual(self.hook.read_bytes(), b"running hook")

    def test_git_cannot_change_checkout_during_publication(self):
        update = updater.check_source_update(self.clone)
        newer = self.newer_commit()
        replace = Path.replace

        def try_to_move_checkout(source, target):
            for args, lock in ((("merge", "--ff-only", newer), "index.lock"),
                               (("update-ref", "HEAD", newer), "HEAD.lock")):
                result = subprocess.run(["git", *args], cwd=self.clone, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(lock, result.stderr)
            return replace(source, target)

        with patch.object(Path, "replace", try_to_move_checkout):
            updater.install_source_update(self.clone, update)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), update.commit)
        self.assertEqual((self.clone / "README.md").read_text(), "Incoming change")
        self.git(self.clone, "merge", "--ff-only", newer)
