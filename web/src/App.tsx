import { Suspense, type ComponentType } from "react";
import { Shell } from "./components/Shell";
import { useI18n } from "./i18n";
import { TourProvider } from "./components/Tour";
import { LoadError, lazyPage } from "./lib/lazyPage";
import { Router, useRouter } from "./lib/router";
import { useWorkspace, WorkspaceProvider } from "./lib/workspace";
import { Analyze } from "./pages/Analyze";

const Landing = lazyPage(() => import("./pages/Landing"));
const Heal = lazyPage(() => import("./pages/Heal"));
const Fool = lazyPage(() => import("./pages/Fool"));
const Agent = lazyPage(() => import("./pages/Agent"));
const Audit = lazyPage(() => import("./pages/Audit"));
const ModelCard = lazyPage(() => import("./pages/ModelCard"));
const About = lazyPage(() => import("./pages/About"));
const Team = lazyPage(() => import("./pages/Team"));
const Contact = lazyPage(() => import("./pages/Contact"));

const ROUTES: Record<string, ComponentType> = {
  "/": Landing,
  "/analyze": Analyze,
  "/heal": Heal,
  "/fool": Fool,
  "/agent": Agent,
  "/audit": Audit,
  "/model": ModelCard,
  "/about": About,
  "/team": Team,
  "/contact": Contact,
};

function NotFound() {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-xl px-6 py-24 text-center">
      <h1 className="text-3xl font-normal">{t("app.notFound")}</h1>
      <p className="mt-3 text-fog-300">{t("app.notFoundBody")}</p>
    </div>
  );
}

function Page() {
  const { path } = useRouter();
  const { t } = useI18n();
  const Component = ROUTES[path.replace(/\/+$/, "") || "/"] ?? NotFound;
  return (
    <LoadError key={path}>
      <Suspense fallback={<div className="px-8 py-24 text-center text-fog-400">{t("app.loading")}</div>}>
        <Component />
      </Suspense>
    </LoadError>
  );
}

/** Presentation sizes scale the whole app (not the tour card, which sits outside) for a projector. */
function Zoomed({ children }: { children: React.ReactNode }) {
  const { zoom } = useWorkspace();
  return <div style={zoom === 1 ? undefined : { zoom }}>{children}</div>;
}

export function App() {
  return (
    <Router>
      <WorkspaceProvider>
        <TourProvider>
          <Zoomed>
            <Shell>
              <Page />
            </Shell>
          </Zoomed>
        </TourProvider>
      </WorkspaceProvider>
    </Router>
  );
}
