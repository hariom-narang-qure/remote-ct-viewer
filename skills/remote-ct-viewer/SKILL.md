---
name: remote-ct-viewer
description: Show a CT scan, optionally with a label-mask overlay (segmentation, prediction, ground truth, nodules), in the user's NiiVue viewer (remote-ct-viewer). Use when the user wants to see, view, look at, inspect, or visualise a scan or mask, or asks to "show me" / "dump" a case. Also use when the user asks about a viewer project, its cases, or the notes they wrote on cases in the viewer. Writes the files as a case (optionally inside a project folder) and replies with the case name to paste into the viewer.
---

# Show a scan in remote-ct-viewer

The viewer serves on `localhost:8000` of this machine. The user reaches it through an SSH tunnel.
In the viewer they paste a case name into the "Open case" box and press Enter, which opens that case
in a new tab. Your job is to write the case and hand them the name.

## Cases and projects

Everything lives under the cases directory (`$REPO/cases`, or `$NOD_CASES_DIR`). A **case** is a folder
with a `scan.nii.gz`. A **project** is any folder that holds cases. Projects can be nested, and the
top-level folder is the root project.

```
cases/
  quick-look/                  case in the root project, id "quick-look"
    scan.nii.gz
  fissures/                    project "fissures"
    project.json               the user's notes on this project's cases (written by the viewer)
    run3/                      sub-project "fissures/run3"
      project.json
      case1/                   case, id "fissures/run3/case1"
        scan.nii.gz            CT in HU
        mask.nii.gz            label map on the scan's grid (optional)
        mask-meta.json         {"labels": {"1": "fissure"}} (optional)
        notes.md               your context for the reviewer, shown beside the scan (optional)
```

- **A case's id is its path below the cases directory.** Use that full path everywhere: as the
  `dump_case.py` name, in the Open case box, and in `#case=<id>` links.
- **The project is the folder holding the case.** It has a page at `http://localhost:8000/projects/<project>/`
  (top level: `/projects/`). The page has a table of the project's cases with the user's notes, plus
  links to its sub-projects.
- **Cases never contain other cases**, and a project folder can't be turned into a case.
- **There are two kinds of notes. Don't mix them up:**
  - `<case>/notes.md` is context *you* write for the reviewer: where the data came from, what to check.
  - `<project>/project.json` is what the *user* wrote in the viewer's "My notes" dialog, keyed by the
    case's folder name (not its full id):
    ```json
    { "cases": { "case1": {
        "notes": "fissure broken at apex",
        "points": [{ "id": "k3j9x0aa", "view": "axial", "slice": 120, "slice_axis": 2,
                     "voxel": [210, 188, 120], "mm": [-61.2, 14.0, -230.5],
                     "note": "gap here", "created": "2026-11-06T10:00:00.000Z" }],
        "updated": "2026-11-06T08:30:56+00:00" } } }
    ```
    `points` are notes the user pinned to one spot on a slice. `view` is the pane they pointed in.
    `voxel` uses the scan file's native index order, so `nib.load(scan).get_fdata()[i, j, k]` is the
    pointed voxel, and `slice == voxel[slice_axis]`. `mm` is world RAS. When you analyse a point,
    index the scan or mask with `voxel`; don't re-derive it from `slice`. To send the user to a
    point, link `http://localhost:8000/#case=<case id>&point=<point id>`.
    Read it when the user refers to their notes, or asks which cases they flagged, accepted, rejected
    and so on. It is the record of the user's review, so don't edit it unless they ask. If you must
    write to it, keep every key you didn't add; other tools may store data there too.
- **Delete mode in 3D saves the edited mask as a new case.** It goes in the same project as the
  original, named `<case>-edit<n>`.

## Steps

0. **Find the repo.** This skill is installed as a symlink into the repo's `skills/` folder:
   ```bash
   REPO=$(dirname "$(dirname "$(readlink -f ~/.claude/skills/remote-ct-viewer)")")
   ```
   All paths below are relative to `$REPO`. Cases go in `$REPO/cases` unless `$NOD_CASES_DIR` is set.

1. **Get the inputs onto disk.** `dump_case.py` reads:
   - `.nii` / `.nii.gz`
   - DICOM series folders, `.nrrd`, `.mha` and anything else SimpleITK reads
   - `.npy`, only with axes in RAS x, y, z order; pass `--spacing` in mm

   If the data only exists in memory in some script, save it as `.nii.gz` with its real affine
   (nibabel), or with `sitk.WriteImage` if it is a SimpleITK image. Put temporary files in the scratchpad.
   Do NOT save `sitk.GetArrayFromImage(...)` output as `.npy`: it is z, y, x in LPS, so it would
   display flipped and transposed.

2. **Pick a case name.**
   - Short, descriptive and unique, e.g. `<series-id>-pred` or `<patient>-gt-vs-pred`.
   - Put related cases in a project by giving a path: `<project>/<case>`, nested if useful
     (`fissures/run3/case1`). Use a project whenever you dump several cases for one review, or when
     the user names one. Reuse an existing project when the new cases belong to it. Missing
     project folders are created.
   - Each path part allows `[A-Za-z0-9._-]` and must start with a letter or digit.
   - Check `ls "$REPO/cases/<project>"`. Never pass `--overwrite` unless the user asked to
     replace that case; choose a new name instead.

3. **Write the case:**
   ```bash
   uv run --project "$REPO" python "$REPO/dump_case.py" <name> \
       --scan <ct> [--mask <label-map>] [--labels '{"1": "nodule", "2": "vessel"}'] \
       [--notes <notes.md>]
   ```
   - The mask is one integer label map holding every overlay, with 0 as background.
   - To show several separate masks (e.g. ground truth and prediction), merge them into one label map
     with a distinct id each, and name them in `--labels`.
   - Labels you don't name still show, named by their number. Name them whenever you know what they mean.
   - The script refuses masks that aren't on the scan's grid. Resample the mask to the scan
     (nearest neighbour) before dumping. Don't work around the check.
   - Probability maps are rejected. Threshold them into labels first.

3a. **Add notes when the reviewer needs context.** The viewer shows `notes.md` from the case folder
   as rendered Markdown in a panel beside the scan. Write notes whenever the case isn't
   self-explanatory: where each mask came from (model, run, file path), what you changed (labels
   removed, resampling, merging), known problems, and what the user should check. Keep them short
   and factual, e.g.:
   ```markdown
   ## Fissure review, case 3
   - **Label 1, fissure:** terra-ridge `edit1` mask, with label 2 (removed lines) set to 0
   - **Label 2, airway:** `/data/airway_cases/.../case3_airway_segmentor.nii.gz`
   - Check the left oblique fissure near the apex; it looked broken in 2D.
   ```
   - For a new case, write the Markdown to a scratchpad file and pass `--notes <file>`.
   - For an existing case, write or edit `$REPO/cases/<case id>/notes.md` directly. It takes effect on
     page reload, with no re-dump and no `--overwrite`. Replacing someone else's notes counts as
     replacing the case, so add to them unless the user asked otherwise.
   - Notes are rendered as sanitised HTML: Markdown, links, tables and code blocks work, scripts don't.

4. **Make sure the server is up.** `curl -sf localhost:8000/api/cases` should succeed. If it fails, start it detached:
   ```bash
   cd "$REPO" && uv sync && setsid nohup .venv/bin/python server.py > server.log 2>&1 < /dev/null &
   ```
   Don't use `pkill -f "python server.py"` to restart it: the pattern matches your own shell command.
   Find the server by its port with `ss -ltnp | grep :8000` instead.

5. **Reply with the case id alone in a code block** so the user can copy it:

   ````
   ```
   <case id>
   ```
   ````
   Then add one line saying what is overlaid, e.g. "label 1 = GT nodule, label 2 = predicted",
   and mention that the case has notes if you wrote any.
   Also mention the direct link `http://localhost:8000/#case=<case id>`. For cases in a project, also
   link the project page `http://localhost:8000/projects/<project>/`, where the user can see all its
   cases and their notes.
   For several cases, give one code block per case. When they share a project, the project link can
   be given once, at the end.
