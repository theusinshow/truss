"use client";

import { PointerEvent, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Crosshair, Eye, Maximize2, Minus, Plus } from "lucide-react";

import { DocumentDetail, Sheet } from "@/lib/projects-api";

type SheetViewerProps = {
  apiBaseUrl: string;
  documents: DocumentDetail[];
};

type PanState = {
  x: number;
  y: number;
};

const minZoom = 0.25;
const maxZoom = 3;

function clampZoom(value: number) {
  return Math.min(maxZoom, Math.max(minZoom, value));
}

export function SheetViewer({ apiBaseUrl, documents }: SheetViewerProps) {
  const sheets = useMemo(
    () =>
      documents.flatMap((document) =>
        document.sheets.map((sheet) => ({
          ...sheet,
          documentName: document.original_filename
        }))
      ),
    [documents]
  );
  const [activeSheetId, setActiveSheetId] = useState("");
  const [zoom, setZoom] = useState(0.55);
  const [pan, setPan] = useState<PanState>({ x: 0, y: 0 });
  const [dragStart, setDragStart] = useState<{
    pointerX: number;
    pointerY: number;
    pan: PanState;
  } | null>(null);

  const activeSheet = sheets.find((sheet) => sheet.id === activeSheetId) ?? sheets[0] ?? null;
  const activeIndex = activeSheet ? sheets.findIndex((sheet) => sheet.id === activeSheet.id) : -1;

  function resetView(nextZoom = 0.55) {
    setZoom(nextZoom);
    setPan({ x: 0, y: 0 });
  }

  function setActiveSheet(sheet: Sheet) {
    setActiveSheetId(sheet.id);
    resetView();
  }

  function moveSheet(offset: number) {
    if (activeIndex < 0 || sheets.length === 0) {
      return;
    }

    const nextIndex = (activeIndex + offset + sheets.length) % sheets.length;
    setActiveSheet(sheets[nextIndex]);
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({
      pointerX: event.clientX,
      pointerY: event.clientY,
      pan
    });
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragStart) {
      return;
    }

    setPan({
      x: dragStart.pan.x + event.clientX - dragStart.pointerX,
      y: dragStart.pan.y + event.clientY - dragStart.pointerY
    });
  }

  if (!activeSheet) {
    return (
      <div className="flex min-h-[520px] items-center justify-center border border-truss-line bg-truss-base p-6 text-center">
        <div>
          <Eye aria-hidden="true" className="mx-auto h-5 w-5 text-truss-accent" />
          <p className="mt-4 font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
            Viewer sem prancha
          </p>
          <p className="mt-3 max-w-md text-sm leading-6 text-truss-muted">
            Importe um PDF em uma revisao para liberar a visualizacao das folhas.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-truss-line bg-truss-base">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-truss-line px-4 py-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
            Prancha ativa
          </p>
          <p className="mt-1 text-sm font-semibold text-truss-text">
            {activeSheet.label}
            {"documentName" in activeSheet ? ` | ${activeSheet.documentName}` : ""}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => moveSheet(-1)}
            title="Folha anterior"
            type="button"
          >
            <ChevronLeft aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => moveSheet(1)}
            title="Proxima folha"
            type="button"
          >
            <ChevronRight aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => resetView()}
            title="Fit"
            type="button"
          >
            <Maximize2 aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => setZoom((current) => clampZoom(current - 0.15))}
            title="Reduzir zoom"
            type="button"
          >
            <Minus aria-hidden="true" className="h-4 w-4" />
          </button>
          <span className="w-14 text-center font-mono text-xs text-truss-muted">
            {Math.round(zoom * 100)}%
          </span>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => setZoom((current) => clampZoom(current + 0.15))}
            title="Ampliar zoom"
            type="button"
          >
            <Plus aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="grid min-h-[620px] grid-cols-[150px_minmax(0,1fr)]">
        <aside className="border-r border-truss-line bg-truss-panel">
          <div className="border-b border-truss-line px-3 py-2 font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
            Folhas
          </div>
          <div className="max-h-[620px] overflow-y-auto">
            {sheets.map((sheet, index) => (
              <button
                className="block w-full border-b border-truss-line px-3 py-3 text-left hover:bg-truss-base data-[active=true]:bg-truss-base"
                data-active={sheet.id === activeSheet.id}
                key={sheet.id}
                onClick={() => setActiveSheet(sheet)}
                type="button"
              >
                <span className="font-mono text-xs text-truss-muted">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="mt-1 block text-sm font-semibold text-truss-text">
                  {sheet.label}
                </span>
                <span className="mt-1 block font-mono text-[11px] text-truss-muted">
                  {Math.round(sheet.width_pt)} x {Math.round(sheet.height_pt)} pt
                </span>
              </button>
            ))}
          </div>
        </aside>

        <div
          className="relative overflow-hidden bg-[linear-gradient(to_right,rgba(154,163,177,0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(154,163,177,0.08)_1px,transparent_1px)] bg-[size:28px_28px]"
          onPointerDown={handlePointerDown}
          onPointerLeave={() => setDragStart(null)}
          onPointerMove={handlePointerMove}
          onPointerUp={() => setDragStart(null)}
          role="presentation"
        >
          <div className="absolute left-3 top-3 z-10 flex items-center gap-2 border border-truss-line bg-truss-panel/95 px-3 py-2 font-mono text-xs text-truss-muted">
            <Crosshair aria-hidden="true" className="h-3.5 w-3.5 text-truss-accent" />
            Pan por arrasto | Coordenadas PDF em pt
          </div>
          <div
            className="flex h-full min-h-[620px] items-center justify-center transition-transform duration-150 ease-out"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- Local rendered PDF sheets need direct transform control. */}
            <img
              alt={`Render da ${activeSheet.label}`}
              className="max-h-none max-w-none select-none border border-truss-line bg-zinc-100 shadow-[0_18px_60px_rgba(0,0,0,0.38)]"
              draggable={false}
              src={`${apiBaseUrl}/sheets/${activeSheet.id}/image`}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
