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

Edited masks (3D delete mode) are the one write path. The browser posts the whole edited mask as
.nii.gz and the server saves it as a new case "<case>-edit<n>", never touching the original:
  1. The upload must have the original mask's shape and may only differ from it by voxels set to 0,
     so a buggy or stale page cannot write anything but deletions.
  2. Its voxels are re-saved under the original mask's header, so the affine and dtype are exactly
     the original's rather than whatever NiiVue's writer produced.
  3. The scan is hard-linked (copied if linking fails), not duplicated, since scans are large.
"""

import gzip
import json
import os
import shutil
from pathlib import Path

import nibabel as nib
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from case_layout import CASES_DIR, MASK_FILE, META_FILE, SCAN_FILE

HERE = Path(__file__).parent
SERVABLE_FILES = {SCAN_FILE, MASK_FILE}

app = FastAPI(title="remote-ct-viewer")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


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


@app.post("/api/cases/{case_id}/edited-mask")
async def save_edited_mask(case_id: str, request: Request):
    source = case_dir(case_id)
    if not (source / MASK_FILE).is_file():
        raise HTTPException(404, f"Case {case_id!r} has no mask")
    body = await request.body()
    new_id = await run_in_threadpool(write_edited_case, source, body)
    return {"id": new_id}


def write_edited_case(source: Path, nii_gz: bytes) -> str:
    original = nib.load(source / MASK_FILE)
    kept = check_only_deletions(np.asanyarray(original.dataobj), read_uploaded_mask(nii_gz))
    target = make_edit_case_dir(source)
    nib.save(nib.Nifti1Image(kept, original.affine, original.header), target / MASK_FILE)
    if (source / META_FILE).is_file():
        shutil.copy2(source / META_FILE, target / META_FILE)
    # Last: a folder only counts as a case once it has a scan, so a failed write never lists a half case.
    link_or_copy(source / SCAN_FILE, target / SCAN_FILE)
    return target.name


def read_uploaded_mask(nii_gz: bytes) -> np.ndarray:
    try:
        return np.asanyarray(nib.Nifti1Image.from_bytes(gzip.decompress(nii_gz)).dataobj)
    except Exception as e:
        raise HTTPException(400, f"Upload is not a readable .nii.gz: {e}")


def check_only_deletions(original: np.ndarray, edited: np.ndarray) -> np.ndarray:
    if edited.shape != original.shape:
        raise HTTPException(400, f"Edited mask shape {edited.shape} != original {original.shape}")
    if not np.all((edited == original) | (edited == 0)):
        raise HTTPException(400, "Edited mask changes voxels other than setting them to 0")
    return np.where(edited == 0, 0, original).astype(original.dtype)


def make_edit_case_dir(source: Path) -> Path:
    n = 1
    while True:
        target = CASES_DIR / f"{source.name}-edit{n}"
        try:
            target.mkdir()
            return target
        except FileExistsError:
            n += 1


def link_or_copy(src: Path, dst: Path):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
