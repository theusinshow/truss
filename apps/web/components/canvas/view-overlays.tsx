"use client";

import { CANVAS_NAVIGATION } from "@/lib/canvas-navigation";
import type { SheetView } from "@/lib/projects-api";

const KIND_LABEL: Record<string, string> = {
  plan: "planta",
  section: "corte",
  detail: "detalhe",
  perspective: "perspectiva",
};

function labelFor(view: SheetView) {
  return view.title_raw ?? KIND_LABEL[view.view_kind] ?? view.view_kind;
}

/**
 * A escala numerica e mais legivel na forma normalizada, mas uma declaracao
 * nao numerica so faz sentido com as palavras da folha: "ESCALA REPRESENTATIVA"
 * e uma declaracao valida, e mostrar vazio no lugar dela pareceria ausencia.
 */
function scaleFor(view: SheetView) {
  return view.declared_scale ?? view.declared_scale_raw;
}

export function ViewOverlays({
  activeViewId,
  onSelect,
  views,
}: {
  activeViewId: string | null;
  onSelect: (view: SheetView) => void;
  views: SheetView[];
}) {
  return (
    <>
      {views.map((view) => {
        const label = labelFor(view);
        const scale = scaleFor(view);

        return (
          <button
            aria-label={`Inspecionar view ${label}`}
            className="absolute border border-dashed border-truss-info/60 bg-truss-info/5 text-left transition-colors hover:bg-truss-info/10 data-[active=true]:border-truss-info data-[active=true]:bg-truss-info/15"
            data-active={view.id === activeViewId}
            key={view.id}
            onClick={(event) => {
              event.stopPropagation();
            }}
            onPointerDown={() => {
              // Sem stopPropagation: o canvas precisa ver o evento para iniciar
              // o pan, e as views cobrem quase toda a folha.
              onSelect(view);
            }}
            style={{
              height: (view.y1 - view.y0) * CANVAS_NAVIGATION.renderScale,
              left: view.x0 * CANVAS_NAVIGATION.renderScale,
              top: view.y0 * CANVAS_NAVIGATION.renderScale,
              width: (view.x1 - view.x0) * CANVAS_NAVIGATION.renderScale,
            }}
            title={`${label}${scale ? ` · ${scale}` : ""} · ${view.provenance}`}
            type="button"
          >
            <span className="absolute -top-5 left-0 flex items-center gap-1.5 whitespace-nowrap border border-truss-info/60 bg-truss-panel px-1.5 py-0.5 font-mono text-[8.5px] uppercase tracking-[0.08em] text-truss-info">
              {view.identifier ? `${view.identifier} ` : ""}
              {label}
              {scale ? ` · ${scale}` : ""}
              {/* Nivel bruto, como esta na folha: normalizar exige confirmacao. */}
              {view.level_raw ? ` · nivel ${view.level_raw}` : ""}
            </span>
          </button>
        );
      })}
    </>
  );
}
