"""First install only. No overwrite, process management, dependencies or secrets."""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from package_files import package_files


def install(custom_nodes: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    target_parent = custom_nodes.resolve(strict=True)
    if custom_nodes.is_symlink() or target_parent.name != "custom_nodes" or not (target_parent.parent / "main.py").is_file():
        raise ValueError("Choose the actual backend ComfyUI/custom_nodes next to main.py.")
    target = target_parent / "ComfyUI-CRUN-Nodes-Next"
    if target.exists() or target.is_symlink():
        raise FileExistsError("CRUN Next destination already exists. No files were changed.")
    if target == root or not target.resolve().is_relative_to(target_parent):
        raise ValueError("Unsafe installation target.")
    sources = package_files(root)  # Complete source checks before creating target.
    target.mkdir()
    for source in sources:
        relative = source.relative_to(root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
            raise RuntimeError("Installed file hash mismatch. Installation is incomplete; no old files were overwritten.")
    return {"installed": str(target), "files": len(sources), "kie_modified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--custom-nodes", type=Path, required=True)
    print(install(parser.parse_args().custom_nodes))
