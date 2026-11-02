/**
 * How the landing brain cracks open (Truth Guardian, after GetLayers' Rift Stone): not three equal parts cut along
 * straight lines, but three unequal ones broken along a stone's crack. The brain is covered by Voronoi cells
 * (RIFT_SCALE cells per unit, the brain's radius being 1.4); each cell goes whole to the nearest of three seeds, so
 * the edges between the parts follow the cells' jagged edges, and the cells' other edges are the fine cracks inside a
 * part. The shader (shaders.ts) draws and moves the parts from the same seeds and cells; this side finds where their
 * names go and which part a point on the screen is on (the scene worker).
 */

export const RIFT_SCALE = 3;
// Depth counts for this much of a cell: the cells run long front to back, so a crack seen from the front stays one line
// over the brain's folds, and what lies behind a part belongs to the same part. Small enough that the whole front half
// sits in one layer of cells: a wall between two layers would face the viewer and light up as a broad patch.
export const RIFT_DEPTH = 0.1;
// x, y of each part's seed: 0 text (upper left), 1 sound (upper right), 2 images (below); off-centre on purpose, so
// the parts come out unequal.
export const RIFT_SEEDS: [number, number][] = [
  [-0.78, 0.62],
  [0.86, 0.4],
  [0.12, -0.82],
];

// The shader's riftHash step for step, in the graphics card's 32-bit numbers, so both sides find the very same cells.
const f = Math.fround;
const fract = (x: number) => f(x - Math.floor(x));
const hash = (x: number, y: number, z: number): [number, number, number] => {
  const a = fract(f(x * f(0.1031))), b = fract(f(y * f(0.103))), c = fract(f(z * f(0.0973)));
  const shift = f(33.33);
  const d = f(f(f(a * f(b + shift)) + f(b * f(a + shift))) + f(c * f(c + shift)));
  const p = f(a + d), q = f(b + d), r = f(c + d);
  return [fract(f(f(p + q) * r)), fract(f(f(p + p) * q)), fract(f(f(q + p) * p))];
};

/** The centre of the Voronoi cell around a point, in model space (the shader's riftCells, nearest feature). */
export function riftCell(x: number, y: number, z: number): [number, number, number] {
  const px = x * RIFT_SCALE, py = y * RIFT_SCALE, pz = z * RIFT_SCALE * RIFT_DEPTH;
  const nx = Math.floor(px), ny = Math.floor(py), nz = Math.floor(pz);
  let best = Infinity;
  let cell: [number, number, number] = [nx, ny, nz];
  for (let k = -1; k <= 1; k++)
    for (let j = -1; j <= 1; j++)
      for (let i = -1; i <= 1; i++) {
        const gx = nx + i, gy = ny + j, gz = nz + k;
        const [hx, hy, hz] = hash(gx, gy, gz);
        const cx = gx + 0.28 + 0.44 * hx;
        const cy = gy + 0.28 + 0.44 * hy;
        const cz = gz + 0.28 + 0.44 * hz;
        const d = (cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2;
        if (d < best) [best, cell] = [d, [cx, cy, cz]];
      }
  return [cell[0] / RIFT_SCALE, cell[1] / RIFT_SCALE, cell[2] / (RIFT_SCALE * RIFT_DEPTH)];
}

/** Which part a cell goes to, by its centre: its nearest seed. */
export function riftPiece(cx: number, cy: number): number {
  let best = 0;
  RIFT_SEEDS.forEach(([sx, sy], i) => {
    const [bx, by] = RIFT_SEEDS[best];
    if ((cx - sx) ** 2 + (cy - sy) ** 2 < (cx - bx) ** 2 + (cy - by) ** 2) best = i;
  });
  return best;
}

/** The way a part moves out when the brain opens (unit length): toward its seed and a little toward the viewer. */
export function riftApart(piece: number): [number, number, number] {
  const [x, y] = RIFT_SEEDS[piece];
  const z = 0.3 * Math.hypot(x, y);
  const n = Math.hypot(x, y, z);
  return [x / n, y / n, z / n];
}
