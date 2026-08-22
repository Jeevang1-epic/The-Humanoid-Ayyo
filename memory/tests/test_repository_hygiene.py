from pathlib import Path
import subprocess
import unittest


class RepositoryHygieneTest(unittest.TestCase):
    def test_runtime_sqlite_files_are_ignored_and_untracked(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        runtime_files = (
            "memory/runtime/owner.sqlite3",
            "memory/runtime/owner.sqlite3-wal",
            "memory/runtime/owner.sqlite3-shm",
        )

        for runtime_file in runtime_files:
            with self.subTest(runtime_file=runtime_file):
                ignored = subprocess.run(
                    ["git", "check-ignore", "--quiet", runtime_file],
                    cwd=repository_root,
                    check=False,
                )
                self.assertEqual(0, ignored.returncode)

        tracked = subprocess.run(
            ["git", "ls-files", "--", "memory/runtime/**"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual("", tracked.stdout)


if __name__ == "__main__":
    unittest.main()
