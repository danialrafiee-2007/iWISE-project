import { ShaderCanvas } from "./ShaderCanvas";
import * as loupe from "./gradients/loupe";
import * as pharos from "./gradients/pharos";
import * as riffle from "./gradients/riffle";

// Each gradient keeps its shipped settings; only the palette keys are recoloured to the app's cream-and-sage
// palette, which is how their makers say to tint them (CONFIG colours, never the shader). The edge vignette is off:
// it darkens toward black, which on a wide cream banner reads as a dirty smudge.

const PHAROS = { ...pharos.CONFIG, bgColor: "#f6f1e4", colorA: "#e7d8bd", colorB: "#d8e4d9", colorC: "#7fa88a", colorD: "#fdfcfa", vignette: 0 };
const LOUPE = { ...loupe.CONFIG, bgColor: "#f6f1e4", colorA: "#e4ece1", colorB: "#cbdcce", colorC: "#7fa88a", colorD: "#5b7fb0", vignette: 0 };
const RIFFLE = { ...riffle.CONFIG, bgColor: "#fbf7ed", colorA: "#f1e7d3", colorB: "#e4ece1", colorC: "#7fa88a", colorD: "#5b7fb0", colorE: "#fdfcfa", vignette: 0 };

export const Pharos = ({ paused, className }: { paused?: boolean; className?: string }) => (
  <ShaderCanvas frag={pharos.FRAG} config={PHAROS} rig="lead" rest={[0.62, 0.4]} paused={paused} className={className} />
);
export const Loupe = ({ paused, className }: { paused?: boolean; className?: string }) => (
  <ShaderCanvas frag={loupe.FRAG} config={LOUPE} rig="chain" paused={paused} className={className} />
);
export const Riffle = ({ paused, className }: { paused?: boolean; className?: string }) => (
  <ShaderCanvas frag={riffle.FRAG} config={RIFFLE} rig="chain" paused={paused} className={className} />
);
