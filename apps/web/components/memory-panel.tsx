"use client";

import { FormEvent, useEffect, useState } from "react";
import { Brain, Trash2 } from "lucide-react";

import { createMemory, deleteMemory, listMemories, Memory } from "@/lib/projects-api";

type MemoryPanelProps = {
  apiBaseUrl: string;
};

export function MemoryPanel({ apiBaseUrl }: MemoryPanelProps) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [key, setKey] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function loadMemories() {
      try {
        const nextMemories = await listMemories(apiBaseUrl);
        if (isMounted) {
          setMemories(nextMemories);
        }
      } catch (loadError) {
        if (isMounted) {
          setError(loadError instanceof Error ? loadError.message : "Falha ao carregar memorias.");
        }
      }
    }

    void loadMemories();

    return () => {
      isMounted = false;
    };
  }, [apiBaseUrl]);

  async function handleCreateMemory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const memory = await createMemory(apiBaseUrl, {
        scope: "global",
        key,
        text
      });
      setMemories((current) => [memory, ...current]);
      setKey("");
      setText("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Falha ao salvar memoria.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDeleteMemory(memoryId: string) {
    setError(null);

    try {
      await deleteMemory(apiBaseUrl, memoryId);
      setMemories((current) => current.filter((memory) => memory.id !== memoryId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Falha ao excluir memoria.");
    }
  }

  return (
    <section className="rounded-lg border border-truss-line bg-truss-panel p-5 shadow-[0_1px_2px_rgba(32,43,61,0.04)]">
      <div className="flex items-center gap-3">
        <Brain aria-hidden="true" className="h-4 w-4 text-truss-accent" />
        <h3 className="text-sm font-semibold text-truss-text">
          Memorias
        </h3>
      </div>

      {error ? <p className="mt-3 rounded-md bg-truss-danger/10 px-3 py-2 text-sm text-truss-danger">{error}</p> : null}

      <form className="mt-5 space-y-3" onSubmit={(event) => void handleCreateMemory(event)}>
        <label className="block">
          <span className="text-xs font-medium text-truss-muted">Chave</span>
        <input
          className="mt-2 w-full border border-truss-line bg-truss-raised px-3 font-mono text-sm text-truss-text outline-none placeholder:text-truss-subtle focus:border-truss-accent"
          maxLength={120}
          onChange={(event) => setKey(event.target.value)}
          placeholder="chave, ex.: escala"
          required
          value={key}
        />
        </label>
        <label className="block">
          <span className="text-xs font-medium text-truss-muted">Regra</span>
        <textarea
          className="mt-2 w-full resize-none border border-truss-line bg-truss-raised px-3 py-2 text-sm text-truss-text outline-none placeholder:text-truss-subtle focus:border-truss-accent"
          maxLength={1200}
          onChange={(event) => setText(event.target.value)}
          placeholder="Regra explicita aprendida"
          required
          value={text}
        />
        </label>
        <button
          className="w-full border border-truss-line bg-truss-raised px-4 text-sm font-semibold text-truss-text transition-colors hover:border-truss-accent hover:bg-truss-accentSoft disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isSubmitting}
          type="submit"
        >
          Salvar memoria
        </button>
      </form>

      <div className="mt-5 space-y-2">
        {memories.length === 0 ? (
          <p className="text-sm leading-6 text-truss-muted">Nenhuma memoria explicita salva.</p>
        ) : (
          memories.map((memory) => (
            <article className="rounded-lg border border-truss-line bg-truss-raised p-3" key={memory.id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-xs font-semibold text-truss-text">{memory.key}</p>
                  <p className="mt-2 text-sm leading-5 text-truss-muted">{memory.text}</p>
                </div>
                <button
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center border border-truss-line bg-truss-panel text-truss-muted transition-colors hover:border-truss-danger/40 hover:bg-truss-danger/10 hover:text-truss-danger"
                  onClick={() => void handleDeleteMemory(memory.id)}
                  title="Excluir memoria"
                  type="button"
                >
                  <Trash2 aria-hidden="true" className="h-4 w-4" />
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
