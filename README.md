# remote-ct-viewer

Minimal NiiVue viewer for CT scans with toggleable label-map overlays.

## Adding a case

One folder per case under `cases/` (or `$NOD_CASES_DIR`):

```
cases/<case_id>/
  scan.nii.gz       CT in HU
  mask.nii.gz       integer label map, same grid as scan, 0 = background (optional)
  mask-meta.json    label names (optional)
```

`mask-meta.json`:

```json
{ "labels": { "1": "lung left", "2": "lung right", "3": "nodule" } }
```

Every label present in the mask is drawn. Labels missing from the meta are named by their number.
New folders show up on page reload; no server restart needed.

`dump_case.py` writes a case from NIfTI, `.npy`, DICOM folders or anything SimpleITK reads,
checking that the mask is on the scan's grid:

```bash
uv run python dump_case.py my-case --scan ct.nii.gz --mask seg.nii.gz --labels '{"1": "nodule"}'
```

## Running

```bash
uv sync
uv run python server.py                          # serves on 127.0.0.1:8000
ssh -L 8000:localhost:8000 <user>@<remote>       # on your laptop, then open http://localhost:8000
```

Paste a case name into the "Open case" box and press Enter to open it in a new tab.
Links like `http://localhost:8000/#case=<case_id>` open a specific case.
In the viewer, scroll to change slices, right-drag to adjust window/level, and click to read HU and the label.

## Claude Code skill

`skills/remote-ct-viewer` lets Claude Code write a case and give you its name. Install it on Linux or macOS
by linking it into your skills folder, from the repo root:

```bash
mkdir -p ~/.claude/skills && ln -sfn "$(pwd)/skills/remote-ct-viewer" ~/.claude/skills/remote-ct-viewer
```

The skill finds the repo through this link, so keep the repo where it is (or run the command again after you move it).
