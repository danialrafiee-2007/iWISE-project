import { Suspense, type ComponentType } from "react";
import { Shell } from "./components/Shell";
import { useI18n } from "./i18n";
import { TourProvider } from "./components/Tour";
import { LoadError, lazyPage } from "./lib/lazyPage";
import { Router, useRouter } from "./lib/router";
import { WorkspaceProvider } from "./lib/workspace";
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
const Examples = lazyPage(() => import("./pages/Examples"));
const Media = lazyPage(() => import("./pages/Media"));

const ROUTES: Record<string, ComponentType> = {
  "/": Landing,
  "/analyze": Analyze,
  "/heal": Heal,
  "/fool": Fool,
  "/agent": Agent,
  "/audit": Audit,
  "/model": ModelCard,
  "/examples": Examples,
  "/audio": Media,
  "/audio/models": Media,
  "/image": Media,
  "/image/models": Media,
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

export function App() {
  return (
    <Router>
      <WorkspaceProvider>
        <TourProvider>
          <Shell>
            <Page />
          </Shell>
        </TourProvider>
      </WorkspaceProvider>
    </Router>
  );
}
