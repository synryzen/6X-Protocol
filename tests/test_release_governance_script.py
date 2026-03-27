import subprocess
import sys
import unittest
from pathlib import Path


class ReleaseGovernanceScriptTests(unittest.TestCase):
    def test_verify_release_governance_baseline(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "verify_release_governance.py"
        self.assertTrue(script.exists(), "verify_release_governance.py should exist")

        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(
                "verify_release_governance.py failed:\n"
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
            )


if __name__ == "__main__":
    unittest.main()
