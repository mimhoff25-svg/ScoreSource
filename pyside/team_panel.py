"""Reusable Tkinter TeamPanel component for ScoreSource.

The panel is a broadcast-style card that lives on a Canvas: rounded corners,
soft shadow, tinted gradient based on the team color, centered logo, and
name/record labels underneath. Designed for a 1280x400 scoreboard row but the
size is configurable (defaults to roughly 420x300).
"""

from __future__ import annotations

import math
import os
import tkinter as tk
from typing import Optional, Union

ColorStr = str
LogoInput = Union[str, tk.PhotoImage, None]

__all__ = ["TeamPanel", "draw_rounded_rect"]


def _hex_to_rgb(color: ColorStr) -> tuple[int, int, int]:
    """Convert a hex color (#RRGGBB or #RGB) to an RGB tuple."""
    value = color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join([c * 2 for c in value])
    if len(value) != 6:
        raise ValueError(f"Invalid hex color: {color}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _blend(color: ColorStr, target: tuple[int, int, int], amount: float) -> str:
    """Mix a base color toward a target color by `amount` (0-1)."""
    base = _hex_to_rgb(color)
    amount = max(0.0, min(1.0, amount))
    mixed = tuple(int(base[i] * (1 - amount) + target[i] * amount) for i in range(3))
    return _rgb_to_hex(mixed)


def draw_rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    curve_depth: float = 0,
    **kwargs,
) -> int:
    """Draw a rounded rectangle on the Canvas using a smoothed polygon, with optional curved top."""
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [x1 + radius, y1]
    if curve_depth > 0:
        num_curve_points = 8
        dx = (x2 - x1 - 2 * radius) / num_curve_points
        for i in range(1, num_curve_points):
            x = x1 + radius + i * dx
            y = y1 + curve_depth * math.sin(math.pi * i / num_curve_points)
            points.extend([x, y])
    points.extend([
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ])
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _edge_offset(radius: float, height: float, y_offset: float) -> float:
    """Curve-aware inset so gradient strips respect the rounded top/bottom."""
    if radius <= 0:
        return 0.0
    if y_offset < radius:
        return radius - math.sqrt(max(radius * radius - (radius - y_offset) ** 2, 0))
    if y_offset > height - radius:
        dy = y_offset - (height - radius)
        return radius - math.sqrt(max(radius * radius - dy * dy, 0))
    return 0.0


def _draw_vertical_gradient(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    start_color: ColorStr,
    end_color: ColorStr,
    steps: int = 70,
    tags: str | tuple[str, ...] | None = None,
) -> None:
    start_rgb = _hex_to_rgb(start_color)
    end_rgb = _hex_to_rgb(end_color)
    height = y2 - y1
    steps = max(1, steps)
    strip_h = height / steps
    for i in range(steps):
        y_start = y1 + i * strip_h
        y_end = y_start + strip_h + 1
        # S-curve for more pronounced curved transition
        t = i / max(1, steps - 1)
        t = (1 - math.cos(math.pi * t)) / 2
        rgb = tuple(int(start_rgb[j] + (end_rgb[j] - start_rgb[j]) * t) for j in range(3))
        color = _rgb_to_hex(rgb)
        offset = max(
            _edge_offset(radius, height, y_start - y1),
            _edge_offset(radius, height, y_end - y1),
        )
        wave = 8 * math.sin(2 * math.pi * (y_start - y1) / height)
        canvas.create_rectangle(
            x1 + offset + wave,
            y_start,
            x2 - offset - wave,
            y_end,
            outline="",
            fill=color,
            tags=tags,
        )


class TeamPanel(tk.Frame):
    """A modern team panel built on a Tkinter Canvas."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        team_color: ColorStr = "#1d428a",
        team_name: str = "TEAM",
        record: str = "0-0",
        logo: LogoInput = None,
        panel_width: int = 420,
        panel_height: int = 230,
        background: ColorStr = "#050b16",
        font_family: str = "Helvetica",
        **kwargs,
    ):
        super().__init__(master, bg=background, **kwargs)
        self.team_color = team_color
        self.team_name = team_name
        self.record = record
        self.panel_width = panel_width
        self.panel_height = panel_height
        self.corner_radius = 26
        self.curve_depth = 20  # Depth of the top curve
        self.background = background
        self.font_family = font_family
        self._logo: tk.PhotoImage | None = None
        self._logo_handle: Optional[int] = None

        canvas_height = panel_height + 24
        self.canvas = tk.Canvas(
            self,
            width=panel_width,
            height=canvas_height,
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            bg=background,
        )
        self.canvas.pack(fill="x", padx=8, pady=(8, 4))

        self.name_label = tk.Label(
            self,
            text=team_name,
            font=(font_family, 20, "bold"),
            fg="#f2f6ff",
            bg=background,
            anchor="center",
        )
        self.name_label.pack(fill="x", padx=8, pady=(0, 2))

        self.record_label = tk.Label(
            self,
            text=record,
            font=(font_family, 13, "bold"),
            fg="#93a6c4",
            bg=background,
            anchor="center",
        )
        self.record_label.pack(fill="x", padx=8)

        self.set_logo(logo)
        self.redraw()

    # Public API -----------------------------------------------------
    def set_team(
        self,
        *,
        team_color: Optional[ColorStr] = None,
        team_name: Optional[str] = None,
        record: Optional[str] = None,
        logo: LogoInput = None,
    ) -> None:
        if team_color:
            self.team_color = team_color
        if team_name:
            self.team_name = team_name
        if record:
            self.record = record
        if logo is not None:
            self.set_logo(logo)
        self.name_label.configure(text=self.team_name)
        self.record_label.configure(text=self.record)
        self.redraw()

    def set_logo(self, logo: LogoInput) -> None:
        """Accepts a PhotoImage or a filesystem path. Sets a centered logo."""
        loaded: tk.PhotoImage | None = None
        if isinstance(logo, tk.PhotoImage):
            loaded = logo
        elif isinstance(logo, str) and logo:
            path = os.fspath(logo)
            if os.path.exists(path):
                try:
                    loaded = tk.PhotoImage(file=path)
                except Exception:
                    loaded = None
        self._logo = loaded
        if self._logo:
            self._logo = self._fit_logo(self._logo, max_size=int(self.panel_height * 0.55))

    # Internal drawing ----------------------------------------------
    def _fit_logo(self, image: tk.PhotoImage, max_size: int) -> tk.PhotoImage:
        """Downsample the logo (integer scale) if it is too large for the panel."""
        w, h = image.width(), image.height()
        scale = max(w / max_size, h / max_size, 1)
        if scale <= 1:
            return image
        factor = math.ceil(scale)
        try:
            return image.subsample(factor, factor)
        except Exception:
            return image

    def redraw(self) -> None:
        """Repaint the panel contents."""
        c = self.canvas
        c.delete("panel")

        # Layout
        pad = 12
        x1 = pad
        y1 = pad
        x2 = x1 + self.panel_width - pad * 2
        y2 = y1 + self.panel_height
        r = self.corner_radius

        # Color palette
        base = self.team_color
        border = _blend(base, (10, 16, 28), 0.7)
        start = _blend(base, (0, 0, 0), 0.28)  # Darker at top
        end = _blend(base, (255, 255, 255), 0.18)  # Lighter at bottom
        shine = _blend(base, (255, 255, 255), 0.35)
        edge_line = _blend(base, (0, 0, 0), 0.55)
        logo_plate = _blend(base, (255, 255, 255), 0.28)
        logo_border = _blend(base, (0, 0, 0), 0.48)

        # Shadow stack (simple offset rectangles for softness).
        shadow_offsets = (10, 7, 4)
        shadow_colors = ("#01040a", "#030813", "#050d1f")
        for off, color in zip(shadow_offsets, shadow_colors):
            draw_rounded_rect(
                c,
                x1 + off,
                y1 + off,
                x2 + off,
                y2 + off,
                r,
                fill=color,
                outline="",
                tags=("panel", "shadow"),
            )

        # Border shell
        draw_rounded_rect(
            c, x1, y1, x2, y2, r, fill=border, outline=border, width=1, tags="panel"
        )

        # Gradient interior
        inner = 6
        _draw_vertical_gradient(
            c,
            x1 + inner,
            y1 + inner,
            x2 - inner,
            y2 - inner,
            max(0, r - inner),
            start,
            end,
            steps=85,
            tags="panel",
        )

        # Subtle top shine
        shine_height = (y2 - y1 - inner * 2) * 0.45
        draw_rounded_rect(
            c,
            x1 + inner + 2,
            y1 + inner + 2,
            x2 - inner - 2,
            y1 + inner + shine_height,
            max(4, r - 10),
            fill=shine,
            outline="",
            tags="panel",
        )

        # Bottom edge accent
        draw_rounded_rect(
            c,
            x1 + inner,
            y2 - inner - 18,
            x2 - inner,
            y2 - inner - 6,
            max(4, r - 12),
            fill=edge_line,
            outline="",
            tags="panel",
        )

        # Logo well (boxed, not circular)
        cx = (x1 + x2) / 2
        cy = y1 + (self.panel_height / 2)
        logo_size = min(self.panel_height * 0.6, self.panel_width * 0.55)
        half = logo_size / 2
        logo_radius = min(14, logo_size * 0.18)  # keep a rectangular feel
        # subtle shadow under the logo box
        draw_rounded_rect(
            c,
            cx - half + 3,
            cy - half + 6,
            cx + half + 3,
            cy + half + 6,
            logo_radius,
            fill="#02060c",
            outline="",
            tags="panel",
        )
        draw_rounded_rect(
            c,
            cx - half,
            cy - half,
            cx + half,
            cy + half,
            logo_radius,
            fill=logo_plate,
            outline=logo_border,
            width=2,
            tags="panel",
        )

        if self._logo:
            self._logo_handle = c.create_image(cx, cy, image=self._logo, tags="panel")
        else:
            c.create_text(
                cx,
                cy,
                text=self.team_name or "TEAM",
                fill="#f7f9ff",
                font=(self.font_family, 26, "bold"),
                tags="panel",
            )


if __name__ == "__main__":
    # Quick demo when running this file directly.
    root = tk.Tk()
    root.configure(bg="#050b16")
    root.title("TeamPanel Demo")
    container = tk.Frame(root, bg="#050b16")
    container.pack(fill="both", expand=True, padx=24, pady=24)

    left = TeamPanel(
        container,
        team_color="#006bb6",
        team_name="KNICKS",
        record="23-12 (6th East)",
    )
    left.pack(side="left", padx=16)

    right = TeamPanel(
        container,
        team_color="#c8102e",
        team_name="BULLS",
        record="19-16 (8th East)",
    )
    right.pack(side="left", padx=16)

    root.mainloop()
