import { healthzResponseSchema } from "@seelice/shared";
import { useEffect, useState } from "react";

type ServerState = "checking" | "online" | "offline";

const serverStateLabel: Record<ServerState, string> = {
  checking: "Vérification du serveur…",
  online: "Serveur en ligne",
  offline: "Serveur injoignable",
};

const serverStateColor: Record<ServerState, string> = {
  checking: "bg-slate-500",
  online: "bg-emerald-500",
  offline: "bg-red-500",
};

async function fetchServerState(signal: AbortSignal): Promise<ServerState> {
  try {
    const response = await fetch("/api/healthz", { signal });
    if (!response.ok) return "offline";
    return healthzResponseSchema.safeParse(await response.json()).success ? "online" : "offline";
  } catch {
    return "offline";
  }
}

export function App() {
  const [serverState, setServerState] = useState<ServerState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    void fetchServerState(controller.signal).then((state) => {
      if (!controller.signal.aborted) setServerState(state);
    });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-950 px-4 text-slate-100">
      <h1 className="text-4xl font-semibold tracking-tight">Seelice</h1>
      <p className="max-w-md text-center text-slate-400">
        Toutes vos caméras IP sur un seul site. L'interface arrive avec les prochains jalons.
      </p>
      <p
        role="status"
        className="flex items-center gap-2 rounded-full border border-slate-800 px-4 py-2 text-sm"
      >
        <span className={`h-2.5 w-2.5 rounded-full ${serverStateColor[serverState]}`} aria-hidden />
        {serverStateLabel[serverState]}
      </p>
    </main>
  );
}
