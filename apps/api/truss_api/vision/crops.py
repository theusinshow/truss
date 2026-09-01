from hashlib import sha256

import fitz

from truss_api.core.settings import Settings
from truss_api.documents import repository as documents_repository
from truss_api.vision.models import RenderedVisionCrop, VisionCandidate


class VisionCropRenderError(Exception):
    pass


def render_vision_crop(
    sheet_id: str,
    candidate: VisionCandidate,
    settings: Settings,
) -> RenderedVisionCrop:
    context = documents_repository.get_sheet_render_context(sheet_id, settings)
    source_path = settings.data_dir / str(context["stored_file_path"])
    if not source_path.exists():
        raise VisionCropRenderError("Source PDF file is missing")

    document = fitz.open(source_path)
    try:
        page = document.load_page(int(context["page_index"]))
        source = fitz.Rect(candidate.bbox_pt)
        clip = fitz.Rect(
            max(page.rect.x0, source.x0 - settings.vision_crop_padding_pt),
            max(page.rect.y0, source.y0 - settings.vision_crop_padding_pt),
            min(page.rect.x1, source.x1 + settings.vision_crop_padding_pt),
            min(page.rect.y1, source.y1 + settings.vision_crop_padding_pt),
        )
        if clip.is_empty or clip.is_infinite:
            raise VisionCropRenderError("Vision candidate produced an invalid crop")

        scale = min(
            settings.vision_render_scale,
            settings.vision_max_crop_pixels / max(float(clip.width), float(clip.height)),
        )
        scale = max(0.5, scale)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
        image_bytes = pixmap.tobytes("png")
    except VisionCropRenderError:
        raise
    except Exception as error:
        raise VisionCropRenderError("Could not render vision crop") from error
    finally:
        document.close()

    crop_hash = sha256(image_bytes).hexdigest()
    relative_path = f"cache/vision-crops/{crop_hash[:2]}/{crop_hash}.png"
    output_path = settings.data_dir / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists():
        output_path.write_bytes(image_bytes)

    return RenderedVisionCrop(
        image_bytes=image_bytes,
        path=relative_path,
        crop_hash=crop_hash,
        crop_bbox_pt=(float(clip.x0), float(clip.y0), float(clip.x1), float(clip.y1)),
        width_px=pixmap.width,
        height_px=pixmap.height,
        scale=scale,
    )
