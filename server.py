"""Serves a directory of CT cases to a NiiVue viewer (static/index.html).

Case layout, one folder per case under CASES_DIR (env NOD_CASES_DIR, default ./cases):

    <case_id>/scan.nii.gz       CT volume in HU
    <case_id>/mask.nii.gz       integer label map on the same grid as the scan, 0 = background
    <case_id>/mask-meta.json    {"labels": {"1": "liver", "2": "nodule"}}

A folder counts as a case only if it has scan.nii.gz. The mask and its meta are optional,
so a scan-only case still opens. Labels present in the mask but missing from the meta are found
by the viewer itself (it scans the loaded volume) and named by their number.

Volumes are rendered entirely in the browser; this server only lists cases and streams files.
Files are looked up by a fixed allowlist of names inside a direct child of CASES_DIR, never by a
client-supplied path, so requests cannot escape the cases directory.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from case_layout import CASES_DIR, MASK_FILE, META_FILE, SCAN_FILE

HERE = Path(__file__).parent
SERVABLE_FILES = {SCAN_FILE, MASK_FILE}

app = FastAPI(title="remote-ct-viewer")


def case_dir(case_id: str) -> Path:
    path = (CASES_DIR / case_id).resolve()
    if path.parent != CASES_DIR or not (path / SCAN_FILE).is_file():
        raise HTTPException(404, f"No case {case_id!r}")
    return path


def read_label_names(path: Path) -> dict[str, str]:
    meta_path = path / META_FILE
    if not meta_path.is_file():
        return {}
    labels = json.loads(meta_path.read_text()).get("labels", {})
    # JSON keys are always strings; normalise so "01" and "1" don't both appear.
    return {str(int(k)): str(v) for k, v in labels.items()}


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/cases")
def list_cases() -> list[str]:
    if not CASES_DIR.is_dir():
        return []
    return sorted(p.name for p in CASES_DIR.iterdir() if (p / SCAN_FILE).is_file())


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    path = case_dir(case_id)
    has_mask = (path / MASK_FILE).is_file()
    return {
        "id": case_id,
        "scan": f"/files/{case_id}/{SCAN_FILE}",
        "mask": f"/files/{case_id}/{MASK_FILE}" if has_mask else None,
        "labels": read_label_names(path) if has_mask else {},
    }


@app.get("/files/{case_id}/{name}")
def get_file(case_id: str, name: str):
    if name not in SERVABLE_FILES:
        raise HTTPException(404)
    file_path = case_dir(case_id) / name
    if not file_path.is_file():
        raise HTTPException(404)
    return FileResponse(file_path, media_type="application/gzip")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
