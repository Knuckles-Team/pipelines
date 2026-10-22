"""Edge-crossing count for precomputed orthogonal layouts."""

from __future__ import annotations

Point = tuple[float, float]


def _segments(points: list) -> list[tuple[Point, Point]]:
    return [(tuple(points[i]), tuple(points[i + 1])) for i in range(len(points) - 1)]


def _cross(a: tuple[Point, Point], b: tuple[Point, Point], eps: float = 0.5) -> bool:
    """True when a horizontal and a vertical segment cross at an interior point."""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    a_h, b_h = abs(ay1 - ay2) < eps, abs(by1 - by2) < eps
    if a_h == b_h:
        return False
    (hx1, hy, hx2), (vx, vy1, vy2) = ((ax1, ay1, ax2), (bx1, by1, by2)) if a_h else ((bx1, by1, bx2), (ax1, ay1, ay2))
    lo_x, hi_x = sorted((hx1, hx2))
    lo_y, hi_y = sorted((vy1, vy2))
    return lo_x + eps < vx < hi_x - eps and lo_y + eps < hy < hi_y - eps


def crossings_in(edges: list[dict]) -> int:
    """Count crossings between segments of different edges that share no endpoint node."""
    total = 0
    for i, first in enumerate(edges):
        for second in edges[i + 1 :]:
            if {first["from"], first["to"]} & {second["from"], second["to"]}:
                continue
            total += sum(1 for s in _segments(first["pts"]) for t in _segments(second["pts"]) if _cross(s, t))
    return total


def count_crossings(layouts: dict) -> dict:
    """Return the total crossing count and the levels that have any."""
    per_level = {nid: crossings_in(lay["edges"]) for nid, lay in layouts.items()}
    return {"total": sum(per_level.values()), "levels": {k: v for k, v in per_level.items() if v}}
