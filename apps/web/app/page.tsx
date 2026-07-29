import { ProjectWorkspace } from "@/components/project-workspace";
import { RuntimeStatus } from "@/components/runtime-status";
import { TrussMark } from "@/components/truss-icons";
import { getRuntimeConfig } from "@/lib/runtime";

export default function Home() {
  const runtime = getRuntimeConfig();

  return (
    <main className="min-h-dvh text-truss-text">
      <section className="flex min-h-dvh flex-col border-x border-truss-line bg-truss-base/88 shadow-truss-panel lg:mx-4 xl:mx-6">
        <header className="sticky top-0 z-30 flex flex-col gap-3 border-b border-truss-line bg-truss-base/90 px-4 py-3 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-8 w-8 items-center justify-center text-truss-accent">
              <TrussMark className="h-6 w-6" />
            </span>
            <div>
              <h1 className="text-base font-semibold leading-5 text-truss-text">
                Truss Agent
              </h1>
              <p className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.09em] text-truss-subtle">
                review-console / pdf-first / local
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
