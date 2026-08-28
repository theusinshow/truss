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
