import { Component, lazy, type ComponentType, type ReactNode } from "react";
import { t } from "../i18n";

const RELOADED = "tg-reloaded-for-new-build";

/** A lazily loaded module that reloads the page once if its chunk is gone (a page left open across a rebuild). */
export function lazyPage<P extends object>(load: () => Promise<{ default: ComponentType<P> }>) {
  return lazy(() =>
    load().then(
      (module) => {
        try {
          sessionStorage.removeItem(RELOADED);
        } catch {
          /* storage unavailable */
        }
        return module;
      },
      (error) => {
        let first = true;
        try {
          first = !sessionStorage.getItem(RELOADED);
          sessionStorage.setItem(RELOADED, "1");
        } catch {
          first = false;
        }
        if (first) {
          window.location.reload();
          return new Promise<never>(() => {});
        }
        throw error;
      },
    ),
  );
}

/** Shown when a page still fails to load after the one reload. */
export class LoadError extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="mx-auto flex max-w-xl flex-col items-center gap-4 px-6 py-24 text-center">
        <h1 className="m-0 text-2xl font-normal">{t("app.loadError")}</h1>
        <p className="m-0 text-fog-300">{t("app.loadErrorBody")}</p>
        <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
          {t("app.reload")}
        </button>
      </div>
    );
  }
}
