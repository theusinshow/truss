"use client";

import { ChevronDown } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";

export type DrawerHeight = "closed" | "default" | "expanded";

const STORAGE_KEY = "truss.findings-drawer.height";

const HEIGHT_CLASS: Record<DrawerHeight, string> = {
  closed: "h-10",
  default: "h-[220px]",
  expanded: "h-[45vh]"
};

const NEXT_HEIGHT: Record<DrawerHeight, DrawerHeight> = {
  closed: "default",
  default: "expanded",
  expanded: "closed"
};

function readStoredHeight(): DrawerHeight {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "closed" || stored === "default" || stored === "expanded") {
      return stored;
    }
  } catch {
    // localStorage pode falhar em janela privada ou com cookies bloqueados
  }

  return "default";
}

type FindingsDrawerProps = {
  children: ReactNode;
  count: number;
  toolbar?: ReactNode;
};

export function FindingsDrawer({ children, count, toolbar }: FindingsDrawerProps) {
  const [height, setHeight] = useState<DrawerHeight>("default");

  useEffect(() => {
    // Ler no efeito (e nao no inicializador) evita divergencia de hidratacao,
    // e o rAF evita render em cascata durante o efeito.
    const frame = window.requestAnimationFrame(() => setHeight(readStoredHeight()));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, height);
    } catch {
      // persistencia e conveniencia, nao requisito
    }
  }, [height]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isEditable =
        target?.tagName === "INPUT"
        || target?.tagName === "TEXTAREA"
        || target?.isContentEditable === true;

      if (isEditable || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }

      if (event.key.toLowerCase() === "a") {
        event.preventDefault();
        setHeight((current) => NEXT_HEIGHT[current]);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const isClosed = height === "closed";

  return (
    <section
      aria-label="Achados da prancha"
      className={`flex shrink-0 flex-col border-t border-truss-line bg-truss-raised transition-[height] duration-200 motion-reduce:transition-none ${HEIGHT_CLASS[height]}`}
    >
      <div className="flex h-10 shrink-0 items-center gap-3 border-b border-truss-line px-3">
        <button
          aria-expanded={!isClosed}
          className="flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.09em] text-truss-subtle transition-colors hover:text-truss-text"
          onClick={() => setHeight((current) => NEXT_HEIGHT[current])}
          title="Alternar altura dos achados (A)"
          type="button"
        >
          <ChevronDown
            aria-hidden="true"
            className={`truss-icon h-3.5 w-3.5 transition-transform duration-200 motion-reduce:transition-none ${
              isClosed ? "-rotate-90" : ""
            }`}
          />
          achados
          <span className="text-truss-text">({count})</span>
        </button>

        {isClosed ? null : <div className="flex min-w-0 flex-1 items-center gap-2">{toolbar}</div>}
      </div>

      {isClosed ? null : (
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      )}
    </section>
  );
}
