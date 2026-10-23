// 📖 Docs: obsidian/frontend/components/brain.md

/**
 * The brain's particle surface, built off the main thread.
 *
 * `sampleSurface` + `computeOcclusion` over 140 000 points took 2.6 s of main
 * thread on a throttled phone (mobile TBT 4.3 s): the page could not respond
 * while it ran. Same functions, same inputs, same output — only the thread
 * changed. The typed arrays come back as transferables (no copy).
 */
import { centerAndScale, computeOcclusion, makeSeeds, sampleSurface } from "./sampling";

export interface BrainGeometryRequest {
  tris: Float32Array;
  count: number;
  radius: number;
}

export interface BrainGeometryResult {
  positions: Float32Array;
  normals: Float32Array;
  occlusion: Float32Array;
  seeds: Float32Array;
}

self.onmessage = (event: MessageEvent<BrainGeometryRequest>) => {
  const { tris, count, radius } = event.data;
  const { positions, normals } = sampleSurface(tris, count);
  centerAndScale(positions, 1.45);
  const occlusion = computeOcclusion(positions, radius);
  const seeds = makeSeeds(positions.length / 3);
  const result: BrainGeometryResult = { positions, normals, occlusion, seeds };
  (self as unknown as Worker).postMessage(result, [
    positions.buffer,
    normals.buffer,
    occlusion.buffer,
    seeds.buffer,
  ]);
};
