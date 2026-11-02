import { Suspense, useEffect, useState, type ComponentType } from "react";
import { Shell } from "./components/Shell";
import { useI18n } from "./i18n";
import { TourProvider } from "./components/Tour";
import { JadeIntro } from "./layers/JadeIntro";
import { LoadError, lazyPage } from "./lib/lazyPage";
import { Router, useRouter } from "./lib/router";
import { WorkspaceProvider } from "./lib/workspace";
// The text pages load with the app, so moving between them never passes through the loading line.
import Agent from "./pages/Agent";
import { Analyze } from "./pages/Analyze";
import Fool from "./pages/Fool";
import ModelCard from "./pages/ModelCard";

const Landing = lazyPage(() => import("./pages/Landing"));
const About = lazyPage(() => import("./pages/About"));
const Team = lazyPage(() => import("./pages/Team"));
const Contact = lazyPage(() => import("./pages/Contact"));
const Media = lazyPage(() => import("./pages/Media"));

const ROUTES: Record<string, ComponentType> = {
  "/": Landing,
  "/analyze": Analyze,
  "/agent": Agent,
  "/fool": Fool,
  "/model": ModelCard,
  "/audio": Media,
  "/audio/models": Media,
  "/image": Media,
  "/image/models": Media,
  "/about": About,
  "/team": Team,
  "/contact": Contact,
};

/** The opening plays when the site starts on its home page, which is where a reload also lands (homeOnReload); a link
 *  to another page and the tour's own link go straight in. */
function Intro() {
  const [on, setOn] = useState(() => window.location.pathname === "/" && !new URLSearchParams(window.location.search).has("tour"));
  useEffect(() => {
    if (!on) document.documentElement.classList.remove("intro");
  }, [on]);
  return on ? <JadeIntro onDone={() => setOn(false)} /> : null;
}

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
          <Intro />
        </TourProvider>
      </WorkspaceProvider>
    </Router>
  );
}
