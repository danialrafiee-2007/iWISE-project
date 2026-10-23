import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { guardAgainstTranslation } from "./lib/translationGuard";
import "./styles.css";

guardAgainstTranslation();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
