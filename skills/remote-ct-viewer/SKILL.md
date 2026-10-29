---
name: remote-ct-viewer
description: Show a CT scan, optionally with a label-mask overlay (segmentation, prediction, ground truth, nodules), in the user's NiiVue viewer (remote-ct-viewer). Use when the user wants to see, view, look at, inspect, or visualise a scan or mask, or asks to "show me" / "dump" a case. Writes the files as a case and replies with the case name to paste into the viewer.
---

# Show a scan in remote-ct-viewer

The viewer serves on `localhost:8000` of this machine. The user reaches it through an SSH tunnel.
In the viewer they paste a case name into the "Open case" box and press Enter, which opens that case
in a new tab. Your job is to write the case and hand them the name.

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
   - Allowed characters: `[A-Za-z0-9._-]`, and the name must start with a letter or digit.
   - Check `ls "$REPO/cases"`. Never pass `--overwrite` unless the user asked to
     replace that case; choose a new name instead.

3. **Write the case:**
   ```bash
   uv run --project "$REPO" python "$REPO/dump_case.py" <name> \
       --scan <ct> [--mask <label-map>] [--labels '{"1": "nodule", "2": "vessel"}']
   ```
   - The mask is one integer label map holding every overlay, with 0 as background.
   - To show several separate masks (e.g. ground truth and prediction), merge them into one label map
     with a distinct id each, and name them in `--labels`.
   - Labels you don't name still show, named by their number. Name them whenever you know what they mean.
   - The script refuses masks that aren't on the scan's grid. Resample the mask to the scan
     (nearest neighbour) before dumping. Don't work around the check.
   - Probability maps are rejected. Threshold them into labels first.

4. **Make sure the server is up.** `curl -sf localhost:8000/api/cases` should succeed. If it fails, start it detached:
   ```bash
   cd "$REPO" && uv sync && setsid nohup .venv/bin/python server.py > server.log 2>&1 < /dev/null &
   ```
   Don't use `pkill -f "python server.py"` to restart it: the pattern matches your own shell command.
   Find the server by its port with `ss -ltnp | grep :8000` instead.

5. **Reply with the case name alone in a code block** so the user can copy it:

   ````
   ```
   <name>
   ```
   ````
   Then add one line saying what is overlaid, e.g. "label 1 = GT nodule, label 2 = predicted".
   Also mention the direct link `http://localhost:8000/#case=<name>`.
   For several cases, give one code block per case.
