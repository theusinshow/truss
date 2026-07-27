import { Activity, Database, FileText, Server } from "lucide-react";
import { RuntimeStatus } from "@/components/runtime-status";
import { getRuntimeConfig } from "@/lib/runtime";

const bootstrapItems = [
  {
    label: "Frontend",
    value: "Next.js shell",
    icon: Activity
  },
  {
    label: "Backend",
    value: "FastAPI local",
    icon: Server
  },
  {
    label: "Storage",
    value: "SQLite + disco local",
    icon: Database
  },
  {
    label: "Escopo",
    value: "M0 Bootstrap",
    icon: FileText
  }
];

export default function Home() {
  const runtime = getRuntimeConfig();

  return (
    <main className="min-h-screen px-5 py-6 sm:px-8 lg:px-10">
      <section className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-7xl flex-col border border-truss-line bg-truss-base/95">
        <header className="flex flex-col gap-4 border-b border-truss-line px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-truss-muted">
              Local drawing review
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal text-truss-text">
              Truss Agent
            </h1>
          </div>
          <RuntimeStatus apiBaseUrl={runtime.apiBaseUrl} />
        </header>

        <div className="grid flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="flex min-h-[520px] flex-col justify-between border-b border-truss-line p-5 lg:border-b-0 lg:border-r">
            <div>
              <p className="max-w-3xl text-lg leading-8 text-truss-text">
                Base local para revisao grafica de pranchas estruturais em PDF. Este
                bootstrap cria o esqueleto executavel sem avancar para importacao,
                auditoria, viewer ou IA.
              </p>

              <div className="mt-8 grid grid-cols-1 border border-truss-line sm:grid-cols-2">
                {bootstrapItems.map((item) => {
                  const Icon = item.icon;

                  return (
                    <div
                      className="min-h-32 border-b border-truss-line p-5 odd:sm:border-r [&:nth-last-child(-n+2)]:sm:border-b-0 last:border-b-0"
                      key={item.label}
                    >
                      <Icon aria-hidden="true" className="h-5 w-5 text-truss-accent" />
                      <p className="mt-5 font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
                        {item.label}
                      </p>
                      <p className="mt-2 text-base font-medium text-truss-text">{item.value}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            <footer className="mt-10 border-t border-truss-line pt-5 font-mono text-xs text-truss-muted">
              PDF-first. Revisoes imutaveis. Coordenadas como dados centrais.
            </footer>
          </section>

          <aside className="bg-truss-panel p-5">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-truss-muted">
              M0 status
            </h2>
            <dl className="mt-6 space-y-5 font-mono text-sm">
              <div>
                <dt className="text-truss-muted">Milestone</dt>
                <dd className="mt-1 text-truss-text">Bootstrap only</dd>
              </div>
              <div>
                <dt className="text-truss-muted">API</dt>
                <dd className="mt-1 break-all text-truss-text">{runtime.apiBaseUrl}</dd>
              </div>
              <div>
                <dt className="text-truss-muted">Next step</dt>
                <dd className="mt-1 text-truss-text">Aguardar M1 aprovado</dd>
              </div>
            </dl>
          </aside>
        </div>
      </section>
    </main>
  );
}
