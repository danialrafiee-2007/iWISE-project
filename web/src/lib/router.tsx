import { createContext, useCallback, useContext, useEffect, useState, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from "react";

const RouterContext = createContext<{ path: string; search: string; navigate: (to: string) => void; consume: () => void }>({ path: "/", search: "", navigate: () => {}, consume: () => {} });

export function Router({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState({ path: window.location.pathname, search: window.location.search });
  useEffect(() => {
    const onPop = () => setLocation({ path: window.location.pathname, search: window.location.search });
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = useCallback((to: string) => {
    if (to === window.location.pathname + window.location.search) return;
    const samePage = to.split("?")[0] === window.location.pathname;
    window.history.pushState(null, "", to);
    setLocation({ path: window.location.pathname, search: window.location.search });
    if (!samePage) window.scrollTo({ top: 0 });
  }, []);
  /** Drop the query once a page has acted on it, so a reload or Back does not repeat the action. */
  const consume = useCallback(() => {
    window.history.replaceState(null, "", window.location.pathname);
    setLocation({ path: window.location.pathname, search: "" });
  }, []);
  return <RouterContext.Provider value={{ ...location, navigate, consume }}>{children}</RouterContext.Provider>;
}

export const useRouter = () => useContext(RouterContext);

export function Link({ to, children, onClick, ...rest }: { to: string } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const { navigate } = useRouter();
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} onClick={handle} {...rest}>
      {children}
    </a>
  );
}
