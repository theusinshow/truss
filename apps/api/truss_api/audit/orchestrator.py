from truss_api.audit import repository
from truss_api.core.settings import Settings


def _full_page_bbox(sheet_context: dict[str, object]) -> dict[str, float]:
    return {
        "x0": 0.0,
        "y0": 0.0,
        "x1": float(sheet_context["width_pt"]),
        "y1": float(sheet_context["height_pt"]),
    }


def _top_band_bbox(sheet_context: dict[str, object]) -> dict[str, float]:
    height = float(sheet_context["height_pt"])
    width = float(sheet_context["width_pt"])
    return {
        "x0": 0.0,
        "y0": 0.0,
        "x1": width,
        "y1": min(height, height * 0.22),
    }


def run_deterministic_audit(sheet_id: str, settings: Settings) -> dict[str, object]:
    sheet_context = repository.get_sheet_context(sheet_id, settings)
    text_blocks = repository.list_text_blocks(sheet_id, settings)
    all_text = "\n".join(str(block["text"]).upper() for block in text_blocks)
    findings: list[dict[str, object]] = []

    if not text_blocks:
        findings.append(
            {
                "category": "identification",
                "type": "unverifiable",
                "description": "Nenhum texto nativo foi detectado nesta folha. A auditoria textual e limitada sem OCR ou analise visual.",
                "severity": "high",
                "confidence": 0.92,
                "bbox": _full_page_bbox(sheet_context),
                "evidence": ["PyMuPDF nao retornou blocos de texto nativo para a pagina."],
            }
        )

    if "ESCALA" not in all_text:
        findings.append(
            {
                "category": "identification",
                "type": "missing_information",
                "description": "Nao foi encontrada indicacao textual de escala na folha.",
                "severity": "medium",
                "confidence": 0.72,
                "bbox": _top_band_bbox(sheet_context),
                "evidence": ["Busca deterministica por 'ESCALA' nos textos nativos da folha."],
            }
        )

    title_terms = ("FORMA", "LOCACAO", "LOCAÇÃO", "CORTE", "DETALHE", "PLANTA")
    if not any(term in all_text for term in title_terms):
        findings.append(
            {
                "category": "identification",
                "type": "attention",
                "description": "Nao foi encontrado titulo tecnico reconhecivel para classificar a prancha.",
                "severity": "medium",
                "confidence": 0.68,
                "bbox": _top_band_bbox(sheet_context),
                "evidence": ["Termos esperados: FORMA, LOCACAO, CORTE, DETALHE ou PLANTA."],
            }
        )

    if not findings:
        findings.append(
            {
                "category": "composition",
                "type": "attention",
                "description": "Auditoria deterministica inicial nao encontrou inconsistencias textuais obvias. Revisao visual ainda e necessaria.",
                "severity": "low",
                "confidence": 0.55,
                "bbox": _full_page_bbox(sheet_context),
                "evidence": ["Primeira passada deterministica concluida sem gatilhos criticos."],
            }
        )

    return repository.create_audit_run(
        sheet_context=sheet_context,
        findings=findings,
        settings=settings,
    )
