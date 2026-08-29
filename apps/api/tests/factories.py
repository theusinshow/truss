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
        ("1 PLANTA DE FORMAS - TERREO", "ESCALA 1:50", 200, 200),
        ("2 CORTE A-A", "ESCALA 1:50", 200, 800),
        ("3 DETALHE 01 LAJE", "ESCALA 1:20", 1300, 800),
    ]
    for title, scale, x, y in views:
        page.insert_text((x, y), title, fontsize=16)
        page.insert_text((x, y + 20), scale, fontsize=6)
        page.insert_text((x + 40, y + 120), "19", fontsize=8)
        page.draw_rect(fitz.Rect(x, y + 40, x + 700, y + 400), color=(0, 0, 0), width=1)

    page.insert_text((320, 340), "NIVEL -0.05", fontsize=8)

    page.insert_text((1750, 1500), "EST-0050-A", fontsize=11)
    page.insert_text((1750, 1520), "CPF: 951.770.276-00", fontsize=11)
    page.insert_text((1750, 1560), "PROJETO ESTRUTURAL", fontsize=11)
    page.insert_text((1750, 1590), "PLANTA DE FORMAS", fontsize=11)

    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()
