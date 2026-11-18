/**
 * Marking connected components of a label map for deletion, in place on NiiVue's image buffer.
 *
 * How marks are stored:
 *   A marked component is shown by overwriting its voxels with `markValue`, a label id no real label
 *   uses, which the viewer colours white. So "is this voxel marked" is just `img[i] === markValue`,
 *   and the edited mask is "copy the buffer, zero every marked voxel". Each mark also keeps the voxel
 *   indices and the label it replaced, so unmarking restores it exactly, even when two marked
 *   components of different labels touch each other.
 *
 * Connectivity:
 *   6-connectivity (face neighbours), matching scipy.ndimage.label's default, so a region found here
 *   is the same region a Python script would find.
 *
 * Indexing:
 *   Everything works on native voxel indices, x + y*nx + z*nx*ny in file order, because that is how
 *   NiiVue keeps `volume.img`. NiiVue reports clicked positions in RAS voxel space; `nativeIndex`
 *   converts them back the same way NiiVue's own getValue does.
 */

export class MaskEditor {
  constructor(volume, markValue) {
    this.img = volume.img;
    this.dims = volume.hdr.dims.slice(1, 4);
    this.markValue = markValue;
    this.marks = [];  // [{label, indices: Int32Array}], in the order they were marked
  }

  isMarked(index) {
    return this.img[index] === this.markValue;
  }

  // A 3D pick lands on the rendered surface, which after rounding is often the empty voxel just
  // outside the region. So fall back to the nearest labelled voxel among the 26 neighbours.
  seedNear(index) {
    if (this.img[index] !== 0) return index;
    const [nx, ny, nz] = this.dims;
    const [x, y, z] = this.coords(index);
    for (let dz = -1; dz <= 1; dz++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const [ax, ay, az] = [x + dx, y + dy, z + dz];
          if (ax < 0 || ay < 0 || az < 0 || ax >= nx || ay >= ny || az >= nz) continue;
          const neighbour = ax + ay * nx + az * nx * ny;
          if (this.img[neighbour] !== 0) return neighbour;
        }
      }
    }
    return -1;
  }

  coords(index) {
    const [nx, ny] = this.dims;
    return [index % nx, Math.floor(index / nx) % ny, Math.floor(index / (nx * ny))];
  }

  // Breadth-first flood fill over voxels of the seed's label. Relabelling a voxel to markValue as it
  // is queued doubles as the "visited" flag, so no separate visited buffer is needed, and the queue
  // ends up holding exactly the component's voxels.
  markComponentAt(seed) {
    const img = this.img, label = img[seed], markValue = this.markValue;
    const [nx, ny, nz] = this.dims, nxy = nx * ny;
    let queue = new Int32Array(4096), head = 0, tail = 0;
    const visit = (i) => {
      if (img[i] !== label) return;
      img[i] = markValue;
      if (tail === queue.length) queue = grow(queue);
      queue[tail++] = i;
    };
    visit(seed);
    while (head < tail) {
      const i = queue[head++];
      const x = i % nx, y = Math.floor(i / nx) % ny, z = Math.floor(i / nxy);
      if (x > 0) visit(i - 1);
      if (x < nx - 1) visit(i + 1);
      if (y > 0) visit(i - nx);
      if (y < ny - 1) visit(i + nx);
      if (z > 0) visit(i - nxy);
      if (z < nz - 1) visit(i + nxy);
    }
    const mark = { label, indices: queue.slice(0, tail) };
    this.marks.push(mark);
    return mark;
  }

  markContaining(index) {
    return this.marks.find((m) => m.indices.includes(index));
  }

  unmark(mark) {
    for (const i of mark.indices) this.img[i] = mark.label;
    this.marks = this.marks.filter((m) => m !== mark);
  }

  clear() {
    for (const mark of [...this.marks]) this.unmark(mark);
  }

  editedImage() {
    const copy = this.img.slice();
    for (const mark of this.marks) {
      for (const i of mark.indices) copy[i] = 0;
    }
    return copy;
  }
}

function grow(queue) {
  const bigger = new Int32Array(queue.length * 2);
  bigger.set(queue);
  return bigger;
}

// One past the highest label, not the top of the array type's range: NiiVue samples the label LUT as a
// texture spanning min..max label id, and once that span reaches ~128 its lookup gets imprecise enough
// that background (0) voxels pick up label 1's colour and the 3D render becomes a solid cube.
// null if the array type cannot hold another value.
export function freeMarkValue(img, labelIds) {
  const value = Math.max(0, ...labelIds) + 1;
  const typeMax = img instanceof Uint8Array ? 255 : img instanceof Int8Array ? 127
    : img instanceof Uint16Array ? 65535 : img instanceof Int16Array ? 32767 : Infinity;
  return value <= typeMax ? value : null;
}

// Mirrors NiiVue's NVImage getValue: RAS voxel -> native voxel via toRASvox, then rounded and clamped.
export function nativeIndex(volume, rasVox) {
  const [x, y, z] = nativeCoords(volume, rasVox);
  const [nx, ny] = volume.hdr.dims.slice(1, 3);
  return x + y * nx + z * nx * ny;
}

export function nativeCoords(volume, rasVox) {
  let [x, y, z] = rasVox;
  const perm = volume.permRAS;
  if (perm[0] !== 1 || perm[1] !== 2 || perm[2] !== 3) {
    const m = volume.toRASvox;  // column-major 4x4, as gl-matrix stores it
    [x, y, z] = [
      m[0] * x + m[4] * y + m[8] * z + m[12],
      m[1] * x + m[5] * y + m[9] * z + m[13],
      m[2] * x + m[6] * y + m[10] * z + m[14],
    ];
  }
  const [nx, ny, nz] = volume.hdr.dims.slice(1, 4);
  const clamp = (v, n) => Math.max(0, Math.min(Math.round(v), n - 1));
  return [clamp(x, nx), clamp(y, ny), clamp(z, nz)];
}

// permRAS[w] is the native axis (1-based, negative if flipped) that NiiVue lines up with world axis w.
export const nativeAxisOfWorld = (volume, worldAxis) => Math.abs(volume.permRAS[worldAxis]) - 1;
