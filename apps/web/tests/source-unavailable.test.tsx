import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";

import { SheetViewer } from "@/components/sheet-viewer";
import type { DocumentDetail } from "@/lib/projects-api";


describe("historical source availability", () => {
  it("explains an unavailable immutable revision instead of showing a broken image", () => {
    const document: DocumentDetail = {
      id: "document-1",
      project_id: "project-1",
      revision_id: "revision-1",
      original_filename: "legacy.pdf",
      stored_file_path: "originals/legacy.pdf",
      content_hash: "abc",
      mime_type: "application/pdf",
      file_size_bytes: 3,
      page_count: 1,
      source_status: "SOURCE_UNAVAILABLE",
      source_reason_code: "clone_migration_missing",
      source_status_note: "Fonte ficou no clone anterior.",
      source_status_at: "2026-09-02T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      sheets: [
        {
          id: "sheet-1",
          document_id: "document-1",
          project_id: "project-1",
          revision_id: "revision-1",
          page_index: 0,
          sheet_number: 1,
          width_pt: 842,
          height_pt: 595,
          rotation: 0,
          label: "Folha 1",
          render_path: null,
          thumbnail_path: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };

    render(
      <SheetViewer
        apiBaseUrl="http://localhost:8000"
        documents={[document]}
        navigationTarget={null}
      />,
    );

    expect(screen.getByText("Fonte historica indisponivel")).toBeInTheDocument();
    expect(screen.getByText(/achados e o feedback desta revisao foram preservados/i)).toBeInTheDocument();
    expect(screen.getByText("SOURCE_UNAVAILABLE / legacy.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
