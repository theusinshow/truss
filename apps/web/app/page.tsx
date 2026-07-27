import { Database } from "lucide-react";
import { ProjectWorkspace } from "@/components/project-workspace";
import { RuntimeStatus } from "@/components/runtime-status";
import { getRuntimeConfig } from "@/lib/runtime";

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
            <div className="mt-2 flex items-center gap-3">
              <Database aria-hidden="true" className="h-7 w-7 text-truss-accent" />
              <h1 className="text-3xl font-semibold tracking-normal text-truss-text">
                Truss Agent
              </h1>
            </div>
          </div>
          <RuntimeStatus apiBaseUrl={runtime.apiBaseUrl} />
        </header>

        <ProjectWorkspace apiBaseUrl={runtime.apiBaseUrl} />
      </section>
    </main>
  );
}
