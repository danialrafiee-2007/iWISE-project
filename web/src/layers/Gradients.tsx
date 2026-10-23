import { ShaderCanvas } from "./ShaderCanvas";
import * as loupe from "./gradients/loupe";
import * as pharos from "./gradients/pharos";
import * as riffle from "./gradients/riffle";

// Each gradient keeps its shipped settings; only the palette keys are recoloured to the app's night-and-teal
// palette, which is how GetLayers says to tint them (CONFIG colours, never the shader).

const PHAROS = { ...pharos.CONFIG, bgColor: "#05070b", colorA: "#0b2f33", colorB: "#14706b", colorC: "#2dd4bf", colorD: "#d9fff6" };
const LOUPE = { ...loupe.CONFIG, bgColor: "#0a1016", colorA: "#0d3b3d", colorB: "#155e63", colorC: "#1f7f7a", colorD: "#7dd3c0" };
const RIFFLE = { ...riffle.CONFIG, bgColor: "#05070b", colorA: "#0b1219", colorB: "#173540", colorC: "#1f6b6a", colorD: "#2dd4bf", colorE: "#ccfbf1" };

export const Pharos = ({ paused, className }: { paused?: boolean; className?: string }) => (
  <ShaderCanvas frag={pharos.FRAG} config={PHAROS} rig="lead" rest={[0.62, 0.4]} paused={paused} className={className} />
);
export const Loupe = ({ paused, className }: { paused?: boolean; className?: string }) => (
  <ShaderCanvas frag={loupe.FRAG} config={LOUPE} rig="chain" paused={paused} className={className} />
);
export const Riffle = ({ paused, className }: { paused?: boolean; className?: string }) => (
  <ShaderCanvas frag={riffle.FRAG} config={RIFFLE} rig="chain" paused={paused} className={className} />
);
