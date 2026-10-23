import { useWorkspace } from "../../lib/workspace";
import { SceneFrame } from "../SceneFrame";

// GetLayers "Glass Halo": two frosted glass rings, shown only while a check runs (in place of a spinner). The page keeps
// it loaded but paused between checks, so starting a check never waits for three.js to load.
export default function GlassHalo({ active }: { active: boolean }) {
  const { reducedMotion } = useWorkspace();
  return (
    <div className="absolute inset-0">
      <SceneFrame name="glass-halo" paused={!active || reducedMotion} eager />
    </div>
  );
}
