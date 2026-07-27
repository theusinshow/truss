import { PanelsTopLeft } from "lucide-react";
import { ProjectWorkspace } from "@/components/project-workspace";
import { RuntimeStatus } from "@/components/runtime-status";
import { getRuntimeConfig } from "@/lib/runtime";

export default function Home() {
  const runtime = getRuntimeConfig();

  return (
    <main className="min-h-dvh px-4 py-4 text-truss-text sm:px-6 lg:px-8">
      <section className="mx-auto flex min-h-[calc(100dvh-2rem)] w-full max-w-[1680px] flex-col overflow-hidden rounded-lg border border-truss-line bg-truss-panel shadow-[0_18px_50px_rgba(32,43,61,0.08)]">
        <header className="flex flex-col gap-4 border-b border-truss-line bg-truss-panel/95 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-lg bg-truss-accent text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.2)]">
              <PanelsTopLeft aria-hidden="true" className="h-5 w-5" />
            </span>
            <div>
              <h1 className="text-[22px] font-semibold leading-7 tracking-normal text-truss-text">
                Truss Agent
              </h1>
              <p className="text-sm leading-5 text-truss-muted">
                Revisão gráfica local para pranchas estruturais em PDF.
              </p>
            </div>
          </div>
          <RuntimeStatus apiBaseUrl={runtime.apiBaseUrl} />
        </header>

        <ProjectWorkspace apiBaseUrl={runtime.apiBaseUrl} />
      </section>
    </main>
  );
}
