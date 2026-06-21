"""Project file storage on local disk (E2E Object Storage in production)."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

from neuralrouter.config import ROOT_DIR

PROJECTS_ROOT = ROOT_DIR / "data" / "projects"
MAX_FILE_BYTES = 512_000
MAX_ZIP_BYTES = 20_000_000
MAX_FILES_PER_PROJECT = 500

SAFE_PATH = re.compile(r"^[a-zA-Z0-9._\-/]+$")


def _project_dir(user_id: str, project_id: str) -> Path:
    return PROJECTS_ROOT / user_id / project_id


def project_root_path(user_id: str, project_id: str) -> Path:
    """Absolute path to a user's cloud project (agent + index root)."""
    return _project_dir(user_id, project_id)


def ensure_storage() -> None:
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


def validate_path(path: str) -> str:
    path = path.replace("\\", "/").strip().lstrip("/")
    if not path or ".." in path or path.startswith("/"):
        raise ValueError("Invalid file path")
    if not SAFE_PATH.match(path):
        raise ValueError("Path contains invalid characters")
    return path


def list_files(user_id: str, project_id: str) -> list[str]:
    root = _project_dir(user_id, project_id)
    if not root.exists():
        return []
    files: list[str] = []
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            files.append(rel)
    return sorted(files)


def read_file(user_id: str, project_id: str, path: str) -> str:
    path = validate_path(path)
    fp = _project_dir(user_id, project_id) / path
    if not fp.is_file():
        raise FileNotFoundError(path)
    data = fp.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File too large")
    return data.decode("utf-8", errors="replace")


def write_file(user_id: str, project_id: str, path: str, content: str) -> dict:
    path = validate_path(path)
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("File too large")
    root = _project_dir(user_id, project_id)
    root.mkdir(parents=True, exist_ok=True)
    fp = root / path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {"path": path, "size_bytes": len(content.encode("utf-8")), "content_hash": digest}


def delete_project_files(user_id: str, project_id: str) -> None:
    root = _project_dir(user_id, project_id)
    if root.exists():
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def import_zip(user_id: str, project_id: str, raw: bytes, project_name: str) -> list[str]:
    if len(raw) > MAX_ZIP_BYTES:
        raise ValueError("Zip too large (max 20MB)")
    ensure_storage()
    root = _project_dir(user_id, project_id)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        count = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").lstrip("/")
            if not name or ".." in name:
                continue
            try:
                name = validate_path(name)
            except ValueError:
                continue
            data = zf.read(info)
            if len(data) > MAX_FILE_BYTES:
                continue
            count += 1
            if count > MAX_FILES_PER_PROJECT:
                raise ValueError("Too many files in zip")
            fp = root / name
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(data)
            written.append(name)
    if not written:
        # seed default if empty zip
        default = f"# {project_name}\n"
        write_file(user_id, project_id, "README.md", default)
        written = ["README.md"]
    return written
