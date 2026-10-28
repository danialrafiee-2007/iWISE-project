import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { homeOnReload } from "./lib/homeOnReload";
import { guardAgainstTranslation } from "./lib/translationGuard";
import "./styles.css";

guardAgainstTranslation();
homeOnReload();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
