"""Regression checks for the exact U30 Air hostapd result bridge patch."""
import shutil
import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/sae-offload/run-fixtures.py"


@unittest.skipUnless(sys.platform.startswith("linux") and
                     (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")),
                     "Linux C compiler and sanitizer runtimes are required")
class SaeOffloadPatchFixtures(unittest.TestCase):
    def test_real_patch_boundary_and_bridge_states(self):
        result = subprocess.run([sys.executable, str(RUNNER)], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("11 firmware-result boundary checks", result.stdout)
        self.assertIn("12 bridge state checks", result.stdout)
        self.assertIn("old unconditional PWE guard is detected", result.stdout)


if __name__ == "__main__":
    unittest.main()
