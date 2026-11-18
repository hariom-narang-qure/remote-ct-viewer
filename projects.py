"""Projects: folders of cases, each with a project.json holding what the user recorded while reviewing.

project.json sits in the project folder, next to its cases:

    {"cases": {"<case folder name>": {
        "notes": "free text",
        "points": [{"id": "p1a2b3", "view": "axial", "slice": 120, "slice_axis": 2,
                    "voxel": [210, 188, 120], "mm": [-61.2, 14.0, -230.5],
                    "note": "fissure gap here", "created": "2026-11-06T10:00:00+00:00"}],
        "updated": "2026-11-06T10:00:00+00:00"}}}

Points are notes pinned to a spot on a slice:
  - view: the 2D view the user pointed in (axial, coronal or sagittal).
  - voxel: the spot in the scan's native voxel indices, i.e. file order, so `scan.get_fdata()[i, j, k]`
    in nibabel is the pointed voxel.
  - slice / slice_axis: voxel[slice_axis], where slice_axis is the native axis closest to the view's
    normal. For a usual axial CT and view "axial" that is the k in `scan[:, :, k]`.
  - mm: the spot in world RAS millimetres, which stays valid even if the scan is resampled.

Cases are keyed by folder name, not full id, so a project folder can be moved or renamed without
rewriting its file. Keys this code doesn't know (in the file or per case) are kept on write, so other
tools can add their own interaction data alongside.

notes.md (written by dump_case.py, read-only in the viewer) is context *for* the reviewer; the notes here
are written *by* the reviewer. They are kept apart so a re-dump never wipes the reviewer's notes.

Writes are read-modify-write of one small file. A lock serialises them within this server, and the file
is replaced atomically (write temp, then rename) so a crash can't leave half-written JSON.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from case_layout import MASK_FILE, NOTES_FILE, PROJECT_FILE, SEGMENT, id_of, is_case

_write_lock = threading.Lock()


def read_project_file(project_dir: Path) -> dict:
    path = project_dir / PROJECT_FILE
    data = json.loads(path.read_text()) if path.is_file() else {}
    data.setdefault("cases", {})
    return data


def write_project_file(project_dir: Path, data: dict):
    fd, tmp = tempfile.mkstemp(dir=project_dir, prefix=".project-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, project_dir / PROJECT_FILE)


def case_entry(case_dir: Path) -> dict:
    return read_project_file(case_dir.parent)["cases"].get(case_dir.name, {})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def update_case_entry(case_dir: Path, **fields) -> dict:
    with _write_lock:
        data = read_project_file(case_dir.parent)
        entry = data["cases"].setdefault(case_dir.name, {})
        entry.update(fields, updated=now_iso())
        write_project_file(case_dir.parent, data)
        return entry


def visible_subdirs(project_dir: Path) -> list[Path]:
    return sorted(p for p in project_dir.iterdir() if p.is_dir() and SEGMENT.match(p.name))


def describe_project(project_dir: Path) -> dict:
    entries = read_project_file(project_dir)["cases"]
    subdirs = visible_subdirs(project_dir)
    return {
        "id": id_of(project_dir),
        "projects": [id_of(p) for p in subdirs if not is_case(p)],
        "cases": [describe_case_row(p, entries.get(p.name, {})) for p in subdirs if is_case(p)],
    }


def describe_case_row(case_dir: Path, entry: dict) -> dict:
    return {
        "id": id_of(case_dir),
        "name": case_dir.name,
        "has_mask": (case_dir / MASK_FILE).is_file(),
        "has_case_notes": (case_dir / NOTES_FILE).is_file(),
        "notes": entry.get("notes", ""),
        "points": entry.get("points", []),
        "updated": entry.get("updated"),
    }


def all_case_ids(root: Path) -> list[str]:
    """Every case at any depth. Case folders are not searched further: cases don't nest."""
    found = []
    for path in visible_subdirs(root):
        if is_case(path):
            found.append(id_of(path))
        else:
            found.extend(all_case_ids(path))
    return found
