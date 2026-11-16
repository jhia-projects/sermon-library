import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { loadLibrary } from "./library";

import type { Library } from "@/types/library";

type State =
  | { status: "loading" }
  | { status: "error"; error: Error; retry: () => void }
  | { status: "ready"; library: Library };

const LibraryContext = createContext<State>({ status: "loading" });

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0); // bump to retry

  useEffect(() => {
    let cancelled = false;
    loadLibrary()
      .then((library) => !cancelled && setState({ status: "ready", library }))
      .catch((error: Error) => {
        if (cancelled) return;
        const retry = () => {
          setState({ status: "loading" });
          setAttempt((n) => n + 1);
        };
        setState({ status: "error", error, retry });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return <LibraryContext.Provider value={state}>{children}</LibraryContext.Provider>;
}

export function useLibraryState(): State {
  return useContext(LibraryContext);
}
