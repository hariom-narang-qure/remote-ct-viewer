"""Writes a scan and optional label mask into the cases directory so the viewer can open them.

Inputs are converted to the layout server.py expects:
  - scan   -> scan.nii.gz, rounded to int16 HU. CT is integral HU anyway, and int16 is half the
              size of float32, so it downloads and loads faster in the browser.
  - mask   -> mask.nii.gz, as the smallest unsigned int type that holds all labels.
  - labels -> mask-meta.json. Labels left out still show in the viewer, named by their number.

Each input is read by the first reader that fits:
  - .nii / .nii.gz: nibabel.
  - .npy: nibabel image with a diagonal affine built from --spacing. The array axes are taken as
    RAS x, y, z. Arrays from SimpleITK's GetArrayFromImage are z, y, x in LPS, so they are NOT
    valid here; write those with sitk.WriteImage to .nii.gz instead.
  - anything else (DICOM folder, .nrrd, .mha, ...): SimpleITK. Its NIfTI writer converts
    LPS to RAS, so we round-trip through a temporary .nii.gz to get a correct affine.

The mask must be on the scan's grid (same shape and affine). We refuse otherwise, because NiiVue
would quietly resample it and the overlay would look plausible but wrong.

Usage:
  uv run --project <repo> python <repo>/dump_case.py NAME --scan CT [--mask MASK]
      [--labels '{"1": "nodule"}'] [--spacing 0.7 0.7 1.25] [--overwrite]
"""

import argparse
import json
import re
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

from case_layout import CASES_DIR, MASK_FILE, META_FILE, SCAN_FILE

CASE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VIEWER_URL = "http://localhost:8000"


def load_image(path: Path, spacing=(1.0, 1.0, 1.0)) -> nib.Nifti1Image:
    if path.name.endswith((".nii", ".nii.gz")):
        return nib.load(path)
    if path.suffix == ".npy":
        return nib.Nifti1Image(np.load(path), np.diag([*spacing, 1.0]))
    return load_with_simpleitk(path)


def load_with_simpleitk(path: Path) -> nib.Nifti1Image:
    import SimpleITK as sitk

    if path.is_dir():
        # Picks the first DICOM series in the folder; pass a folder holding a single series.
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(path)))
        image = reader.Execute()
    else:
        image = sitk.ReadImage(str(path))

    with tempfile.TemporaryDirectory() as tmp:
        nii_path = Path(tmp) / "image.nii.gz"
        sitk.WriteImage(image, str(nii_path))
        nii = nib.load(nii_path)
        # Read into memory before the temp dir is deleted; nibabel loads lazily.
        return nib.Nifti1Image(np.asanyarray(nii.dataobj), nii.affine)


def to_int16_hu(scan: nib.Nifti1Image) -> nib.Nifti1Image:
    hu = np.rint(np.asanyarray(scan.dataobj))
    return nib.Nifti1Image(np.clip(hu, -32768, 32767).astype(np.int16), scan.affine)


def to_label_map(mask: nib.Nifti1Image) -> nib.Nifti1Image:
    data = np.asanyarray(mask.dataobj)
    labels = np.rint(data)
    if not np.allclose(data, labels):
        raise ValueError("Mask has non-integer values; expected a label map (threshold probabilities first)")
    if labels.min() < 0:
        raise ValueError("Mask has negative labels")
    dtype = np.min_scalar_type(int(labels.max()))
    return nib.Nifti1Image(labels.astype(dtype), mask.affine)


def check_same_grid(scan: nib.Nifti1Image, mask: nib.Nifti1Image):
    if scan.shape[:3] != mask.shape[:3]:
        raise ValueError(f"Mask shape {mask.shape} differs from scan shape {scan.shape}")
    if not np.allclose(scan.affine, mask.affine, atol=1e-3):
        raise ValueError(f"Mask affine differs from scan affine:\n{mask.affine}\nvs\n{scan.affine}")


def prepare_case_dir(name: str, overwrite: bool) -> Path:
    if not CASE_NAME.match(name):
        raise ValueError(f"Case name {name!r} must match {CASE_NAME.pattern}")
    case_dir = CASES_DIR / name
    if case_dir.exists() and not overwrite:
        raise FileExistsError(f"Case {name!r} already exists; pick another name or pass overwrite")
    case_dir.mkdir(parents=True, exist_ok=True)
    # Clear old files so a stale mask or meta from a previous dump can't linger.
    for file_name in (SCAN_FILE, MASK_FILE, META_FILE):
        (case_dir / file_name).unlink(missing_ok=True)
    return case_dir


def write_case(name, scan, mask=None, labels=None, overwrite=False) -> Path:
    """scan and mask are nibabel images. labels maps label id -> display name."""
    scan = to_int16_hu(scan)
    if mask is not None:
        mask = to_label_map(mask)
        check_same_grid(scan, mask)

    case_dir = prepare_case_dir(name, overwrite)
    nib.save(scan, case_dir / SCAN_FILE)
    if mask is not None:
        nib.save(mask, case_dir / MASK_FILE)
    if labels:
        meta = {"labels": {str(int(k)): str(v) for k, v in labels.items()}}
        (case_dir / META_FILE).write_text(json.dumps(meta, indent=2) + "\n")
    return case_dir


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="case name, shown in the viewer and pasted into its Open case box")
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--labels", type=json.loads, help='JSON object, e.g. \'{"1": "nodule"}\'')
    parser.add_argument("--spacing", type=float, nargs=3, default=(1.0, 1.0, 1.0), help="mm, only for .npy")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    scan = load_image(args.scan, args.spacing)
    mask = load_image(args.mask, args.spacing) if args.mask else None
    case_dir = write_case(args.name, scan, mask, args.labels, args.overwrite)
    print(f"Wrote {case_dir}")
    print(f"Case: {args.name}")
    print(f"URL:  {VIEWER_URL}/#case={args.name}")


if __name__ == "__main__":
    main()
