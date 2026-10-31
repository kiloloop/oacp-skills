"""Fixtures for memory_lock.sh, run against a throwaway OACP_HOME.

    python3 -m unittest discover -s skills/self-improve/tests   (pytest runs it too)
"""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "memory_lock.sh"


class MemoryLock(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / "projects" / "demo").mkdir(parents=True)
        self.lock = self.home / "projects" / "demo" / ".memory-write.lock"

    def tearDown(self):
        self._tmp.cleanup()

    def run_script(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *args], env={**os.environ, "OACP_HOME": str(self.home)},
                              capture_output=True, text=True)

    def test_acquire_then_second_acquire_is_locked_then_release(self):
        self.assertEqual(self.run_script("acquire", "demo").stdout.strip(), "Lock acquired")
        self.assertTrue(self.run_script("acquire", "demo").stdout.startswith("LOCKED"))
        self.assertEqual(self.run_script("release", "demo").stdout.strip(), "Lock released")
        self.assertFalse(self.lock.exists())

    def test_stale_lock_is_broken(self):
        self.lock.mkdir()
        old = time.time() - 11 * 60
        os.utime(self.lock, (old, old))
        self.assertEqual(self.run_script("acquire", "demo").stdout.strip(), "Lock acquired")

    def test_missing_project_fails_loud_instead_of_reporting_locked(self):
        out = self.run_script("acquire", "nope")
        self.assertEqual(out.returncode, 2)
        self.assertIn("NO_SUCH_PROJECT", out.stderr)


if __name__ == "__main__":
    unittest.main()
