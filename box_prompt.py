"""The box tool: draw a box on a slice, and a fissure model paints the one sheet inside it on a slab of slices.

The model runs in its own process, the box-prompt service of muse_train
(`scripts/fissure/box_prompt_service.py`), so this server needs no torch or GPU. Set BOX_PROMPT_URL if
it is not on http://127.0.0.1:8010.

Flow of one box:
1. The page posts the plane and the box's two corners in world mm, as NiiVue reports a right-drag.
2. This server passes them on with the case's scan path. The service replies with the painted voxels,
   in the scan file's own voxel indices.
3. The voxels are written into box-prompt.nii.gz in the case folder, on the scan's grid, under a new label.
   - Each box gets the next label, so undo removes exactly the last box's voxels.
   - A voxel painted by two boxes keeps the later label.
   - The scan and mask.nii.gz are never touched.
4. The reply carries the painted voxels as flat indices of the file (x fastest, as NiiVue holds `volume.img`).
   So the page paints them into the overlay it already has, instead of reloading a 100M-voxel file per box.

The label volume of the last case is kept in memory, keyed by the file's mtime, so a box does not re-read it.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal, NamedTuple

import nibabel as nib
import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel, Field

from case_layout import BOX_PROMPT_FILE, SCAN_FILE

SERVICE_URL = os.environ.get("BOX_PROMPT_URL", "http://127.0.0.1:8010")
MAX_LABEL = 255   # uint8 file


class BoxRequest(BaseModel):
    plane: Literal["axial", "coronal", "sagittal"]
    mm_start: list[float] = Field(min_length=3, max_length=3)
    mm_end: list[float] = Field(min_length=3, max_length=3)


def service_is_up() -> bool:
    try:
        urllib.request.urlopen(SERVICE_URL, timeout=2)
    except urllib.error.HTTPError:
        return True   # it answered, just not to GET /
    except OSError:
        return False
    return True


def predict_voxels(scan: Path, box: BoxRequest) -> np.ndarray:
    payload = json.dumps({"scan": str(scan), **box.model_dump()}).encode()
    request = urllib.request.Request(f"{SERVICE_URL}/predict", payload, {"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return np.array(json.loads(response.read())["voxels"], dtype=np.int64).reshape(-1, 3)
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"Box service: {json.loads(e.read()).get('detail', e.reason)}")
    except OSError as e:
        raise HTTPException(503, f"Box service not reachable at {SERVICE_URL}: {e}")


class Boxes(NamedTuple):
    labels: np.ndarray   # uint8, the scan's file grid
    affine: np.ndarray


_cached: dict[Path, tuple[int, Boxes]] = {}


def read_boxes(case: Path) -> Boxes:
    path = case / BOX_PROMPT_FILE
    if not path.is_file():
        scan = nib.load(case / SCAN_FILE)
        return Boxes(np.zeros(scan.shape[:3], np.uint8), scan.affine)
    mtime = path.stat().st_mtime_ns
    if case in _cached and _cached[case][0] == mtime:
        return _cached[case][1]
    image = nib.load(path)
    return Boxes(np.asarray(image.dataobj).astype(np.uint8), image.affine)


def write_boxes(case: Path, boxes: Boxes) -> None:
    tmp = case / f".{BOX_PROMPT_FILE}"
    nib.save(nib.Nifti1Image(boxes.labels, boxes.affine), tmp)
    tmp.replace(case / BOX_PROMPT_FILE)   # atomic, so the page never loads a half-written file
    _cached.clear()
    _cached[case] = ((case / BOX_PROMPT_FILE).stat().st_mtime_ns, boxes)


def flat_indices(voxels: np.ndarray, shape) -> list[int]:
    return np.ravel_multi_index(tuple(voxels.T), shape, order="F").tolist()


def add_box(case: Path, box: BoxRequest) -> dict:
    voxels = predict_voxels(case / SCAN_FILE, box)
    boxes = read_boxes(case)
    label = int(boxes.labels.max()) + 1
    if label > MAX_LABEL:
        raise HTTPException(409, f"{MAX_LABEL} boxes already; clear some first")
    boxes.labels[tuple(voxels.T)] = label
    write_boxes(case, boxes)
    return {"label": label, "voxels": len(voxels), "indices": flat_indices(voxels, boxes.labels.shape)}


def undo_last(case: Path) -> dict:
    if not (case / BOX_PROMPT_FILE).is_file():
        return {"label": None}
    boxes = read_boxes(case)
    label = int(boxes.labels.max())
    if label:
        boxes.labels[boxes.labels == label] = 0
        write_boxes(case, boxes)
    return {"label": label or None}


def clear(case: Path) -> dict:
    (case / BOX_PROMPT_FILE).unlink(missing_ok=True)
    _cached.pop(case, None)
    return {"cleared": True}
