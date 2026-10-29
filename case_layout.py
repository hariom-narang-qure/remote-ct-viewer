"""On-disk layout of a case, shared by the server and dump_case.py."""

import os
from pathlib import Path

CASES_DIR = Path(os.environ.get("NOD_CASES_DIR", Path(__file__).parent / "cases")).resolve()

SCAN_FILE = "scan.nii.gz"
MASK_FILE = "mask.nii.gz"
META_FILE = "mask-meta.json"
