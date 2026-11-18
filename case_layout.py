"""On-disk layout of cases and projects, shared by the server and dump_case.py.

A case id is a "/"-separated path under CASES_DIR, e.g. "fissures/run3/case1". The folder holding a
case is its project ("fissures/run3"); top-level cases belong to the root project (""). Projects are
plain folders, so they nest freely, but a case folder never holds other cases.

Every path segment must match SEGMENT. Since a segment can't start with "." this also rules out ".."
and hidden folders, so an id can never point outside CASES_DIR.
"""

import os
import re
from pathlib import Path

CASES_DIR = Path(os.environ.get("NOD_CASES_DIR", Path(__file__).parent / "cases")).resolve()

SCAN_FILE = "scan.nii.gz"
MASK_FILE = "mask.nii.gz"
META_FILE = "mask-meta.json"
NOTES_FILE = "notes.md"
PROJECT_FILE = "project.json"
BOX_PROMPT_FILE = "box-prompt.nii.gz"   # sheets painted with the box tool, one label per box

SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def split_id(rel_path: str) -> list[str] | None:
    """Segments of a case or project id, or None if any segment is invalid. "" is the root project."""
    parts = rel_path.strip("/").split("/") if rel_path.strip("/") else []
    return parts if all(SEGMENT.match(p) for p in parts) else None


def path_for(rel_path: str) -> Path | None:
    parts = split_id(rel_path)
    if parts is None:
        return None
    path = CASES_DIR.joinpath(*parts)
    # Segments are safe, but a symlinked folder could still lead outside CASES_DIR.
    return path if path.resolve().is_relative_to(CASES_DIR) else None


def is_case(path: Path) -> bool:
    return (path / SCAN_FILE).is_file()


def id_of(path: Path) -> str:
    return path.relative_to(CASES_DIR).as_posix() if path != CASES_DIR else ""


def project_id_of(case_id: str) -> str:
    return case_id.rpartition("/")[0]
