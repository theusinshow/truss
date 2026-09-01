from io import BytesIO

import fitz


SYNTHETIC_CATEGORIES = ("PLANTA DE LOCACAO", "PLANTA DE FORMAS", "PLANTA DE ARMADURAS")


def make_structural_pdf_bytes(page_count: int = 3) -> bytes:
    """Prancha estrutural sintetica: moldura + carimbo no canto inferior direito."""
    document = fitz.open()

    for index in range(page_count):
        page = document.new_page(width=1000, height=800)
        page.draw_rect(fitz.Rect(20, 10, 970, 770))
        page.insert_text((120, 200), "L33 h=13")
        page.insert_text((710, 706), f"EST-{(index + 1) * 10:04d}-A")
        page.insert_text((710, 716), f"DETALHAMENTO GENERICO {index + 1}")
        page.insert_text((710, 726), "CPF: 951.770.276-00")
        page.insert_text((710, 741), "PROJETO ESTRUTURAL")
        page.insert_text((710, 756), SYNTHETIC_CATEGORIES[index % len(SYNTHETIC_CATEGORIES)])

    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def make_forms_sheet_pdf_bytes() -> bytes:
    """Planta de formas sintetica: moldura, carimbo e tres views com titulo e escala."""
    document = fitz.open()
    page = document.new_page(width=2384, height=1684)
    page.draw_rect(fitz.Rect(71, 29, 2356, 1656), color=(0, 0, 0), width=2)

    views = [
        ("1 PLANTA DE FORMAS - TERREO", "ESCALA 1:50", 200, 600, 100),
        ("2 CORTE A-A", "ESCALA 1:50", 200, 1200, 700),
        ("3 DETALHE 01 LAJE", "ESCALA 1:20", 1300, 1200, 700),
    ]
    for title, scale, x, y, drawing_top in views:
        page.insert_text((x, y), title, fontsize=16)
        page.insert_text((x, y + 20), scale, fontsize=6)
        page.insert_text((x + 40, drawing_top + 120), "19", fontsize=8)
        page.draw_rect(
            fitz.Rect(x, drawing_top, x + 700, y - 20),
            color=(0, 0, 0),
            width=1,
        )

    page.insert_text((320, 340), "NIVEL -0.05", fontsize=8)

    page.insert_text((1750, 1500), "EST-0050-A", fontsize=11)
    page.insert_text((1750, 1520), "CPF: 951.770.276-00", fontsize=11)
    page.insert_text((1750, 1560), "PROJETO ESTRUTURAL", fontsize=11)
    page.insert_text((1750, 1590), "PLANTA DE FORMAS", fontsize=11)
    # Como no material real, o carimbo tem categoria (a disciplina) e titulo
    # (o conteudo). Sem o titulo, a regra de coerencia nao tem o que comparar.
    page.insert_text((1750, 1610), "PLANTA BAIXAS E PERSPECTIVAS", fontsize=11)

    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _add_pillar_sheet(
    document: fitz.Document,
    *,
    sheet_code: str,
    title: str,
    category: str,
    codes: tuple[str, ...],
) -> None:
    page = document.new_page(width=2384, height=1684)
    page.draw_rect(fitz.Rect(71, 29, 2356, 1656), color=(0, 0, 0), width=2)
    page.draw_rect(fitz.Rect(200, 100, 1500, 560), color=(0, 0, 0), width=1)
    for index, code in enumerate(codes):
        page.insert_text((320 + index * 180, 300), code, fontsize=12)

    page.insert_text((200, 600), f"1 {title}", fontsize=16)
    page.insert_text((200, 620), "ESCALA 1:50", fontsize=7)
    page.insert_text((1750, 1500), sheet_code, fontsize=11)
    page.insert_text((1750, 1520), "CPF: 951.770.276-00", fontsize=11)
    page.insert_text((1750, 1560), "PROJETO ESTRUTURAL", fontsize=11)
    page.insert_text((1750, 1590), category, fontsize=11)
    page.insert_text((1750, 1610), title, fontsize=11)


def make_pillar_forms_pdf_bytes(codes: tuple[str, ...] = ("P1", "P2")) -> bytes:
    document = fitz.open()
    _add_pillar_sheet(
        document,
        sheet_code="EST-0010-A",
        title="PLANTA DE FORMAS - TERREO",
        category="PLANTA DE FORMAS",
        codes=codes,
    )
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def make_pillar_details_pdf_bytes(codes: tuple[str, ...] = ("P1",)) -> bytes:
    document = fitz.open()
    _add_pillar_sheet(
        document,
        sheet_code="EST-0020-A",
        title="DETALHAMENTO PILARES",
        category="PLANTA DE ARMADURAS",
        codes=codes,
    )
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def make_cross_sheet_pillar_pdf_bytes(
    detail_codes: tuple[str, ...] = ("P1",),
) -> bytes:
    document = fitz.open()
    _add_pillar_sheet(
        document,
        sheet_code="EST-0010-A",
        title="PLANTA DE FORMAS - TERREO",
        category="PLANTA DE FORMAS",
        codes=("P1", "P2"),
    )
    _add_pillar_sheet(
        document,
        sheet_code="EST-0020-A",
        title="DETALHAMENTO PILARES",
        category="PLANTA DE ARMADURAS",
        codes=detail_codes,
    )
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def make_pillar_continuity_pdf_bytes(
    *,
    lifecycle_code: str = "P1(MORRE)",
    upper_codes: tuple[str, ...] = ("P1", "P2", "P3", "P4"),
) -> bytes:
    document = fitz.open()
    _add_pillar_sheet(
        document,
        sheet_code="EST-0100-A",
        title="PLANTA DE FORMAS - TERREO (NIVEL 100)",
        category="PLANTA DE FORMAS",
        codes=(lifecycle_code, "P2", "P3", "P4"),
    )
    _add_pillar_sheet(
        document,
        sheet_code="EST-0200-A",
        title="PLANTA DE FORMAS - 1 PAVIMENTO (NIVEL 200)",
        category="PLANTA DE FORMAS",
        codes=upper_codes,
    )
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()
