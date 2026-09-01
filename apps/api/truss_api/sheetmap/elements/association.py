from dataclasses import replace

from truss_api.sheetmap.elements.models import DetectedElement
from truss_api.sheetmap.views.models import DetectedView


def _center_inside(
    bbox: tuple[float, float, float, float],
    view_bbox: tuple[float, float, float, float],
) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return (
        view_bbox[0] <= center_x <= view_bbox[2]
        and view_bbox[1] <= center_y <= view_bbox[3]
    )


def associate_elements(
    elements: list[DetectedElement],
    views: list[DetectedView],
    *,
    sheet_scopes: tuple[str, ...],
) -> list[DetectedElement]:
    associated: list[DetectedElement] = []
    sheet_scope = sheet_scopes[0] if len(sheet_scopes) == 1 else None

    for element in elements:
        candidates = [
            index for index, view in enumerate(views) if _center_inside(element.bbox, view.bbox)
        ]
        attributes = dict(element.attributes)

        if len(candidates) == 1:
            view_index = candidates[0]
            technical_scope = views[view_index].technical_scope or sheet_scope
            attributes["association_status"] = "view_matched"
        elif len(candidates) > 1:
            view_index = None
            technical_scope = None if len(sheet_scopes) > 1 else sheet_scope
            attributes["association_status"] = "ambiguous_views"
            attributes["candidate_view_indexes"] = candidates
        else:
            view_index = None
            technical_scope = sheet_scope
            attributes["association_status"] = (
                "sheet_scope_only" if sheet_scope else "outside_views"
            )

        associated.append(
            replace(
                element,
                view_index=view_index,
                technical_scope=technical_scope,
                attributes=attributes,
            )
        )

    return associated

