"""Local control-mark inspection; extraction is independent of permission to reuse an answer."""

import math
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image

from bd_packet_builder.visual import NormalizedBox

ControlState = Literal["selected", "unselected", "ambiguous"]
CONTROL_VERSION = "historical-control-pixels-v3"


@dataclass(frozen=True)
class ControlPixels:
    state: ControlState
    pixel_box: tuple[int, int, int, int]
    interior_ink_fraction: float


def inspect_control(png: bytes, proposed: NormalizedBox) -> ControlPixels:
    """Reconcile outline and connected-check evidence in a bounded hint neighborhood.

    Only clearly empty or clearly marked interiors are classified. Dots, uncertain outlines
    and competing controls require review; an unselected control is never a negative answer.
    """
    with Image.open(BytesIO(png)) as source:
        width, height = source.size
        left, top, right, bottom = proposed.display_points(width, height)
        w, h = right - left, bottom - top
        if not (6 <= w <= width * 0.06 and 6 <= h <= height * 0.06 and 0.5 <= w / h <= 2):
            raise ValueError("control_geometry_invalid")
        x0, y0 = max(0, math.floor(left - w)), max(0, math.floor(top - 2 * h))
        x1, y1 = min(width, math.ceil(right + w)), min(height, math.ceil(bottom + h / 2))
        with source.crop((x0, y0, x1, y1)).convert("L") as crop:
            cw, ch = crop.size
            pixels = crop.tobytes()
            dark = {(x, y) for y in range(ch) for x in range(cw) if pixels[y * cw + x] < 150}
    components = _components(dark)
    mark = _checkmark(components, w, h, left - x0, top - y0)
    candidates: list[tuple[int, int, int, int]] = []
    runs: list[tuple[int, int, int]] = []
    for y in range(ch):
        x = 0
        while x < cw:
            if (x, y) not in dark:
                x += 1
                continue
            start = x
            while x < cw and (x, y) in dark:
                x += 1
            if 0.35 * w <= x - start <= 1.4 * w:
                runs.append((start, y, x))
    for ax, b, cx in runs:
        for aa, yy, cc in runs:
            a, c = max(ax, aa), min(cx, cc)
            d = yy + 1
            bh = d - b
            if (
                abs(ax - aa) > max(2, w * 0.30)
                or abs(cx - cc) > max(2, w * 0.30)
                or not 0.35 * h <= bh <= 1.4 * h
                or min(c - a, bh) < 6
                or not 0.5 <= (c - a) / bh <= 2
            ):
                continue
            if abs(x0 + (a + c) / 2 - (left + right) / 2) > w / 2:
                continue
            if abs(y0 + (b + d) / 2 - (top + bottom) / 2) > h / 2:
                continue
            edges = (
                sum((a, y) in dark for y in range(b, d)) / bh,
                sum((c - 1, y) in dark for y in range(b, d)) / bh,
            )
            if min(edges) >= 0.65:
                candidates.append((a, b, c, d))
    candidates.sort(key=lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1]), reverse=True)
    center_x, center_y = (left + right) / 2 - x0, (top + bottom) / 2 - y0
    rings: list[tuple[int, int, int, int]] = []

    def ring_matches(a: int, b: int, c: int, d: int) -> bool:
        rx, ry = (c - a) / 2, (d - b) / 2
        ring_x, ring_y = (a + c - 1) / 2, (b + d - 1) / 2
        return (
            min(rx, ry) >= 5
            and 0.5 <= rx / ry <= 2
            and abs(ring_x - center_x) <= w / 2
            and abs(ring_y - center_y) <= h / 2
            and sum(
                any(
                    (
                        round(ring_x + rx * radius * math.cos(angle)),
                        round(ring_y + ry * radius * math.sin(angle)),
                    )
                    in dark
                    for radius in (0.90, 0.95, 1.0, 1.05)
                )
                for angle in (2 * math.pi * i / 72 for i in range(72))
            )
            / 72
            >= 0.90
        )

    # Pixel components anchor intact outlines independently of the model's padding.
    for component in components:
        bounds = _bounds(component)
        if ring_matches(*bounds):
            rings.append(bounds)
    if not rings:
        for offset_x in (-0.2, -0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15, 0.2):
            for offset_y in (-0.2, -0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15, 0.2):
                for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
                    rx, ry = w * scale / 2, h * scale / 2
                    ring_x, ring_y = center_x + w * offset_x, center_y + h * offset_y
                    coverage = (
                        sum(
                            any(
                                (
                                    round(ring_x + rx * radius * math.cos(angle)),
                                    round(ring_y + ry * radius * math.sin(angle)),
                                )
                                in dark
                                for radius in (0.90, 0.95, 1.0, 1.05)
                            )
                            for angle in (2 * math.pi * i / 72 for i in range(72))
                        )
                        / 72
                    )
                    if coverage >= 0.90 and min(rx, ry) >= 5:
                        rings.append(
                            (
                                round(ring_x - rx),
                                round(ring_y - ry),
                                round(ring_x + rx),
                                round(ring_y + ry),
                            )
                        )
    if rings:
        rings.sort(key=lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1]), reverse=True)
        candidates.extend(rings)
    if mark is not None:
        ma, mb, mc, md = _bounds(mark)
        if any(c <= ma or a >= mc or d <= mb or b >= md for a, b, c, d in candidates):
            raise ValueError("control_outline_not_resolved")
        # A tiny loop made by the check's own ink must not suppress the complete shape.
        candidates = [
            rect
            for rect in candidates
            if not (
                ma <= rect[0] < rect[2] <= mc
                and mb <= rect[1] < rect[3] <= md
                and (rect[2] - rect[0]) * (rect[3] - rect[1]) < (mc - ma) * (md - mb) / 4
                and all(
                    point in mark
                    for point in dark
                    if rect[0] <= point[0] < rect[2] and rect[1] <= point[1] < rect[3]
                )
            )
        ]
    if not candidates:
        if mark is not None:
            a, b, c, d = _bounds(mark)
            return ControlPixels("selected", (x0 + a, y0 + b, x0 + c, y0 + d), 0.0)
        raise ValueError("control_outline_not_resolved")
    candidates.sort(key=lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1]), reverse=True)
    a, b, c, d = candidates[0]
    # Rectangle and ellipse fits on one physical outline are not competing controls.
    if any(_overlap((a, b, c, d), other) < 0.8 for other in candidates[1:]):
        raise ValueError("control_outline_not_resolved")
    inset_x, inset_y = max(2, round((c - a) * 0.22)), max(2, round((d - b) * 0.22))
    interior = [
        (x, y) in dark
        for y in range(b + inset_y, d - inset_y)
        for x in range(a + inset_x, c - inset_x)
    ]
    fraction = sum(interior) / len(interior)
    state: ControlState = (
        "unselected" if fraction == 0 else "selected" if fraction >= 0.10 else "ambiguous"
    )
    return ControlPixels(state, (x0 + a, y0 + b, x0 + c, y0 + d), fraction)


def _bounds(points: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    return (
        min(x for x, _ in points),
        min(y for _, y in points),
        max(x for x, _ in points) + 1,
        max(y for _, y in points) + 1,
    )


def _overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    a, b, c, d = first
    e, f, g, h = second
    intersection = max(0, min(c, g) - max(a, e)) * max(0, min(d, h) - max(b, f))
    return intersection / min((c - a) * (d - b), (g - e) * (h - f))


def _components(dark: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(dark)
    components: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        pending = [seed]
        while pending:
            x, y = pending.pop()
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                point = x + dx, y + dy
                if point in remaining:
                    remaining.remove(point)
                    component.add(point)
                    pending.append(point)
        components.append(component)
    return components


def _checkmark(
    components: list[set[tuple[int, int]]],
    w: float,
    h: float,
    left: float,
    top: float,
) -> set[tuple[int, int]] | None:
    """Require a connected descending short arm and ascending long arm near the control."""
    matches: list[set[tuple[int, int]]] = []
    for component in components:
        columns: dict[int, list[int]] = {}
        for x, y in component:
            columns.setdefault(x, []).append(y)
        a, c = min(columns), max(columns)
        if not 0.8 * w <= c - a <= 2 * w:
            continue
        centers = [(x, sum(ys) / len(ys)) for x, ys in sorted(columns.items())]
        trough = max(centers, key=lambda p: p[1])
        trough_x, trough_y = trough
        # Edge antialiasing and attached outlines make a single extreme column unreliable.
        start = min(
            (point for point in centers if point[0] <= min(trough_x, a + (c - a) * 0.3)),
            key=lambda point: point[1],
        )
        end = min(
            (point for point in centers if point[0] >= max(trough_x, c - (c - a) * 0.2)),
            key=lambda point: point[1],
        )
        component_height = max(y for _, y in component) - min(y for _, y in component) + 1
        if not (
            a + (c - a) * 0.15 <= trough_x <= a + (c - a) * 0.65
            and left - 0.2 * w <= trough_x <= left + 1.1 * w
            and top + 0.25 * h <= trough_y <= top + 1.2 * h
            and trough_y - start[1] >= 0.10 * (c - a)
            and trough_y - end[1] >= 0.5 * (c - a)
        ):
            continue

        def coverage(
            first: tuple[int, float],
            last: tuple[int, float],
            columns: dict[int, list[int]] = columns,
            tolerance: float = max(1, 0.08 * component_height),
        ) -> float:
            steps = max(1, last[0] - first[0])
            return sum(
                any(
                    abs(py - (first[1] + (last[1] - first[1]) * i / steps)) <= tolerance
                    for py in columns.get(first[0] + i, ())
                )
                for i in range(steps + 1)
            ) / (steps + 1)

        if min(coverage(start, trough), coverage(trough, end)) >= 0.9:
            matches.append(component)
    return matches[0] if len(matches) == 1 else None
