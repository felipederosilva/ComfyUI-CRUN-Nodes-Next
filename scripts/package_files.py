"""Shared release/install allowlist. Never collect user credentials or caches."""
from pathlib import Path

ROOT_FILES = ("__init__.py", "nodes.py", "generated_nodes.py", "pyproject.toml", "requirements.txt", "LICENSE", "README.md", "ROADMAP.md", "SECURITY.md", "VALIDATION.md")


def package_files(root: Path) -> list[Path]:
    paths = [root / name for name in ROOT_FILES]
    for directory, suffixes in (("crun", {".py"}), ("web", {".js", ".css"}), ("docs", {".md", ".png"}), ("data", {".json"}), ("example_workflows", {".json"})):
        paths.extend(path for path in (root / directory).rglob("*") if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts)
    paths.extend(root / "scripts" / name for name in ("install.py", "package_files.py"))
    result = sorted(set(paths))
    for path in result:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Unsafe or missing package member: {path.name}")
    return result
