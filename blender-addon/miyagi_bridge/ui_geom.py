"""Pure projection helpers for the bridge's /ui object boxes. No bpy, no mathutils: tests run them anywhere.

    persmat = matrix(rv3d.perspective_matrix)       # 4 x 4 rows of floats (a mathutils.Matrix iterates its rows)
    project(persmat, (x, y, z), width, height)      # region pixels, origin bottom-left; None behind the view
    object_box(corners, persmat, width, height)     # an object's screen box from its 8 world bound-box corners
    point_box(origin, persmat, width, height)       # a light / camera / empty: a POINT_BOX_PX square around it

project() mirrors bpy_extras.view3d_utils.location_3d_to_region_2d: prj = M . (x, y, z, 1); prj.w <= 0 (behind the
view) is None; else (w/2 + w/2 * prj.x / prj.w, h/2 + h/2 * prj.y / prj.w).

An object box is kept only when every corner projects (none behind the view), the box's centre is inside the region
and at least MIN_VISIBLE_SHARE of its area survives clipping to the region; the clipped box is returned. A wrong box
is worse than none: anything odd (a degenerate box, a NaN, a short matrix) is None.
"""

from __future__ import annotations

import math

POINT_BOX_PX = 24.0
MIN_VISIBLE_SHARE = 0.5


def matrix(m) -> list[list[float]]:
    """A 4 x 4 matrix as rows of floats; ValueError for any other shape."""
    rows = [[float(v) for v in row] for row in m]
    if len(rows) != 4 or any(len(r) != 4 for r in rows):
        raise ValueError("not a 4x4 matrix")
    return rows


def apply(m: list[list[float]], p) -> tuple[float, float, float]:
    """An affine 4 x 4 matrix applied to a 3D point (matrix_world @ corner)."""
    x, y, z = (float(v) for v in p)
    return tuple(r[0] * x + r[1] * y + r[2] * z + r[3] for r in m[:3])  # type: ignore[return-value]


def project(persmat: list[list[float]], p, width: float, height: float) -> tuple[float, float] | None:
    """A world point in region pixels (origin bottom-left), or None when it is behind the view."""
    x, y, z = (float(v) for v in p)
    px, py, _, pw = (r[0] * x + r[1] * y + r[2] * z + r[3] for r in persmat)
    if not pw > 0.0:
        return None
    hw, hh = width / 2.0, height / 2.0
    out = (hw + hw * (px / pw), hh + hh * (py / pw))
    return out if all(math.isfinite(v) for v in out) else None


def _inside(x: float, y: float, width: float, height: float) -> bool:
    return 0.0 <= x <= width and 0.0 <= y <= height


def _clip(x0: float, y0: float, x1: float, y1: float, width: float, height: float
          ) -> tuple[float, float, float, float] | None:
    cx0, cy0, cx1, cy1 = max(0.0, x0), max(0.0, y0), min(float(width), x1), min(float(height), y1)
    return (cx0, cy0, cx1, cy1) if cx1 > cx0 and cy1 > cy0 else None


def object_box(corners, persmat: list[list[float]], width: float, height: float
               ) -> tuple[float, float, float, float] | None:
    """(x, y, w, h) in region pixels of an object's world-space bound-box corners, clipped to the region; None when a
    corner is behind the view, the centre is outside the region, or less than half of the box is visible."""
    if width <= 0 or height <= 0:
        return None
    pts = [project(persmat, c, width, height) for c in corners]
    if not pts or any(p is None for p in pts):
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    area = (x1 - x0) * (y1 - y0)
    if not area > 0.0 or not _inside((x0 + x1) / 2, (y0 + y1) / 2, width, height):
        return None
    c = _clip(x0, y0, x1, y1, width, height)
    if c is None or (c[2] - c[0]) * (c[3] - c[1]) < MIN_VISIBLE_SHARE * area:
        return None
    return c[0], c[1], c[2] - c[0], c[3] - c[1]


def point_box(origin, persmat: list[list[float]], width: float, height: float, size: float = POINT_BOX_PX
              ) -> tuple[float, float, float, float] | None:
    """(x, y, w, h) of a size-px square around a point-like object's origin, clipped to the region; None when the
    origin is behind the view or outside the region."""
    if width <= 0 or height <= 0:
        return None
    p = project(persmat, origin, width, height)
    if p is None or not _inside(p[0], p[1], width, height):
        return None
    h = size / 2.0
    c = _clip(p[0] - h, p[1] - h, p[0] + h, p[1] + h, width, height)
    return (c[0], c[1], c[2] - c[0], c[3] - c[1]) if c is not None else None
