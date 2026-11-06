# remote-ct-viewer

Minimal NiiVue viewer for CT scans with toggleable label-map overlays.

## Adding a case

One folder per case under `cases/` (or `$NOD_CASES_DIR`):

```
cases/<case_id>/
  scan.nii.gz       CT in HU
  mask.nii.gz       integer label map, same grid as scan, 0 = background (optional)
  mask-meta.json    label names (optional)
  notes.md          Markdown notes shown in a panel beside the viewer (optional)
```

`mask-meta.json`:

```json
{ "labels": { "1": "lung left", "2": "lung right", "3": "nodule" } }
```

Every label present in the mask is drawn. Labels missing from the meta are named by their number.
New folders show up on page reload; no server restart needed.

`notes.md` is any Markdown: where the data came from, what was cleaned, what to look for. It is
rendered (sanitised) in a right-hand panel whenever the case has one, and can be hidden with ×.
Edit the file and reload the page to update it. Cases made by 3D delete keep a copy of the notes.

### Projects

Cases can be grouped into project folders, nested as deep as you like. The case id is then its path,
e.g. `fissures/run3/case1`, and the folder holding a case is its project:

```
cases/fissures/run3/
  project.json      your notes per case, written by the viewer
  case1/scan.nii.gz ...
  case2/scan.nii.gz ...
```

`http://localhost:8000/projects/fissures/run3/` lists the project's cases with your notes in a table, plus
links to sub-projects; `/projects/` is the top level. In the viewer, "My notes" opens a dialog to write
notes on the open case; they are saved in the project's `project.json`:

```json
{ "cases": { "case1": { "notes": "fissure broken at apex", "updated": "2026-11-06T08:30:56+00:00" } } }
```

These are separate from `notes.md`, so re-dumping a case never wipes what you wrote. Other keys in
`project.json` are preserved, so tools can store more interaction data there.

`dump_case.py` writes a case from NIfTI, `.npy`, DICOM folders or anything SimpleITK reads,
checking that the mask is on the scan's grid:

```bash
uv run python dump_case.py my-case --scan ct.nii.gz --mask seg.nii.gz --labels '{"1": "nodule"}' \
    --notes notes.md
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
The "3D render" button toggles a volume render of the masks. Tick "Show scan" to render the CT around
them too (bone, skin or soft tissue preset, adjustable opacity); it is off by default because it is slower.

### Deleting mask regions (3D)

In 3D, "Delete mode" lets you remove connected components from the mask:

1. Double-click a region: its connected component (same label, 6-connected) turns white and is listed.
2. Double-click a white region, or press its ×, to unmark it.
3. "Delete N → new case" saves a copy of the mask with the marked components set to 0 as a new case
   `<case>-edit<n>` in the same project, sharing the scan. The original case is never modified.

## Claude Code skill

`skills/remote-ct-viewer` lets Claude Code write a case and give you its name. Install it on Linux or macOS
by linking it into your skills folder, from the repo root:

```bash
SRC="$(pwd)/skills/remote-ct-viewer"
[ -f "$SRC/SKILL.md" ] || { echo "SKILL.md not found in $SRC"; exit 1; }
mkdir -p ~/.claude/skills && ln -sfn "$SRC" ~/.claude/skills/remote-ct-viewer
```

The skill finds the repo through this link, so keep the repo where it is (or run the command again after you move it).


