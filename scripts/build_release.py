"""Build a credential-free downloadable runtime package with CRC/hash checks."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from package_files import package_files


def main():
    root = Path(__file__).resolve().parents[1]
    version = re.search(r'VERSION = "([0-9.]+)"', (root / "crun/version.py").read_text()).group(1)
    destination = root / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / f"ComfyUI-CRUN-Nodes-Next-v{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        for path in package_files(root):
            relative = path.relative_to(root)
            stream.write(path, "ComfyUI-CRUN-Nodes-Next/" + relative.as_posix())
    with zipfile.ZipFile(archive) as stream:
        if stream.testzip() is not None:
            raise RuntimeError("Archive CRC verification failed")
        members = stream.namelist()
        if any("credentials" in name or "__pycache__" in name or "/.git/" in name for name in members):
            raise RuntimeError("Unsafe archive contents")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Built {archive.name}: {len(members)} members, SHA256 {digest}")


if __name__ == "__main__":
    main()
