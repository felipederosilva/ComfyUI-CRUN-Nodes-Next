import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from install import install
    from package_files import package_files
finally:
    sys.path.pop(0)


class InstallTests(unittest.TestCase):
    def test_first_install_and_refuse_existing_destination(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "main.py").write_text("# fixture", encoding="utf-8")
            (root / "custom_nodes").mkdir()
            receipt = install(root / "custom_nodes")
            target = Path(receipt["installed"])
            self.assertTrue((target / "__init__.py").is_file())
            self.assertFalse((target / ".git").exists())
            self.assertFalse((target / "tests").exists())
            self.assertFalse(receipt["kie_modified"])
            with self.assertRaises(FileExistsError):
                install(root / "custom_nodes")

    def test_requires_actual_backend_location(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "custom_nodes").mkdir()
            with self.assertRaises(ValueError):
                install(root / "custom_nodes")

    def test_allowlist_excludes_caches_secrets_and_git(self):
        files = [path.relative_to(ROOT).as_posix() for path in package_files(ROOT)]
        self.assertIn("crun/client.py", files)
        self.assertIn("web/crun_next.js", files)
        self.assertFalse(any("credentials" in value or "__pycache__" in value or value.startswith(".git/") for value in files))


if __name__ == "__main__":
    unittest.main()
