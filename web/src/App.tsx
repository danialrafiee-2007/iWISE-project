import { lazy, Suspense, type ComponentType } from "react";
import { Shell } from "./components/Shell";
import { Router, useRouter } from "./lib/router";
import { WorkspaceProvider } from "./lib/workspace";
import { Analyze } from "./pages/Analyze";

const Landing = lazy(() => import("./pages/Landing"));
const Heal = lazy(() => import("./pages/Heal"));
const Fool = lazy(() => import("./pages/Fool"));
const Agent = lazy(() => import("./pages/Agent"));
const Audit = lazy(() => import("./pages/Audit"));
const ModelCard = lazy(() => import("./pages/ModelCard"));

const ROUTES: Record<string, ComponentType> = {
  "/": Landing,
  "/analyze": Analyze,
  "/heal": Heal,
  "/fool": Fool,
  "/agent": Agent,
  "/audit": Audit,
  "/model": ModelCard,
};

function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-6 py-24 text-center">
      <h1 className="text-3xl font-normal">Page not found</h1>
      <p className="mt-3 text-fog-300">Use the menu above to open one of the tools.</p>
    </div>
  );
}

function Page() {
  const { path } = useRouter();
  const Component = ROUTES[path.replace(/\/+$/, "") || "/"] ?? NotFound;
  return (
    <Suspense fallback={<div className="px-8 py-24 text-center text-fog-400">Loading…</div>}>
      <Component />
    </Suspense>
  );
}

export function App() {
  return (
    <Router>
      <WorkspaceProvider>
        <Shell>
          <Page />
        </Shell>
      </WorkspaceProvider>
    </Router>
  );
}
