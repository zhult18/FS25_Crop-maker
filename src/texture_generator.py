"""Generate placeholder PNG textures for FS25 crop types.

Each texture is clearly marked as a placeholder so modders know to replace
the files with their actual artwork.  The generated textures have the correct
dimensions and channel layout expected by the FS25 foliage shader.

Texture files produced
----------------------
{name}_DIFFUSE.png   – RGBA colour atlas (atlasSize × atlasSize grid)
{name}_NORMAL.png    – RGB tangent-space normal map atlas (flat, pointing up)
{name}_ROUGHNESS.png – Grayscale roughness atlas
icon_fruitType_{name}.png – 128×128 RGBA minimap / UI icon
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Pillow is required for texture generation.  "
        "Install it with:  pip install Pillow"
    ) from exc

from .utils import CropConfig, FOLIAGE_COLORS, ensure_dir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FONT: Optional[ImageFont.ImageFont] = None


def _get_font(size: int = 12) -> ImageFont.ImageFont:
    global _FONT
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except (OSError, AttributeError):
        pass
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", size)
    except (OSError, AttributeError):
        pass
    return ImageFont.load_default()


def _lerp_color(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between colours *a* and *b* (t in [0, 1])."""
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _draw_foliage_cell(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    cell_w: int,
    cell_h: int,
    state: int,
    total_states: int,
    base_color: tuple[int, int, int],
    foliage_type: str,
) -> None:
    """Draw a single growth-state cell into *draw* at pixel offset (x, y)."""
    progress = state / max(total_states - 1, 1)

    # Background: dark soil → mature green → golden yellow for grain at harvest
    if foliage_type == "grain" and progress > 0.7:
        # Ripening: shift toward golden
        bg = _lerp_color(base_color, (200, 170, 50), (progress - 0.7) / 0.3)
    else:
        soil = (80, 60, 40)
        bg = _lerp_color(soil, base_color, min(progress * 1.5, 1.0))

    draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], fill=(*bg, 220))

    # Draw simplified plant silhouette ────────────────────────────────────────
    plant_h = int(cell_h * 0.1 + cell_h * 0.7 * progress)
    stem_x = x + cell_w // 2
    stem_color = (*base_color, 255)
    stem_dark = (max(base_color[0] - 40, 0), max(base_color[1] - 40, 0), max(base_color[2] - 40, 0), 255)

    if foliage_type == "row_crop":
        # Tall stalk
        draw.line([(stem_x, y + cell_h), (stem_x, y + cell_h - plant_h)], fill=stem_color, width=max(2, cell_w // 32))
        # Leaves
        if progress > 0.2:
            leaf_spread = int(cell_w * 0.25 * progress)
            lh = int(plant_h * 0.4)
            draw.polygon([
                (stem_x, y + cell_h - int(plant_h * 0.4)),
                (stem_x - leaf_spread, y + cell_h - int(plant_h * 0.4) - lh // 2),
                (stem_x, y + cell_h - int(plant_h * 0.4) - lh),
            ], fill=stem_color)
            draw.polygon([
                (stem_x, y + cell_h - int(plant_h * 0.6)),
                (stem_x + leaf_spread, y + cell_h - int(plant_h * 0.6) - lh // 2),
                (stem_x, y + cell_h - int(plant_h * 0.6) - lh),
            ], fill=stem_color)
        # Ear / cob at maturity
        if progress > 0.6:
            ear_y = y + cell_h - plant_h
            draw.ellipse([stem_x - cell_w // 10, ear_y - cell_h // 10,
                          stem_x + cell_w // 10, ear_y + cell_h // 10], fill=(200, 160, 40, 255))
    elif foliage_type == "root_crop":
        # Bushy low foliage
        num_leaves = max(2, int(6 * progress))
        for i in range(num_leaves):
            angle = math.radians(i * 360 / num_leaves)
            lx = stem_x + int(math.cos(angle) * cell_w * 0.2 * progress)
            ly = (y + cell_h - plant_h // 2) + int(math.sin(angle) * cell_h * 0.15 * progress)
            draw.ellipse([lx - cell_w // 16, ly - cell_h // 16,
                          lx + cell_w // 16, ly + cell_h // 16], fill=stem_color)
    elif foliage_type == "grass":
        # Multiple thin blades
        num_blades = max(3, int(8 * progress))
        for i in range(num_blades):
            bx = x + int(cell_w * (i + 0.5) / num_blades)
            curve = int(cell_w * 0.05 * (i % 2 * 2 - 1))
            draw.line([(bx, y + cell_h), (bx + curve, y + cell_h - plant_h)],
                      fill=stem_color, width=max(1, cell_w // 40))
    else:
        # Generic grain / oilseed / legume: simple stem + head
        draw.line([(stem_x, y + cell_h), (stem_x, y + cell_h - plant_h)],
                  fill=stem_color, width=max(1, cell_w // 32))
        if progress > 0.5:
            head_h = int(cell_h * 0.12 * progress)
            draw.ellipse([stem_x - cell_w // 12, y + cell_h - plant_h - head_h,
                          stem_x + cell_w // 12, y + cell_h - plant_h + head_h // 2],
                         fill=stem_dark)

    # Label: state index ───────────────────────────────────────────────────
    label_size = max(8, cell_w // 16)
    font = _get_font(label_size)
    label = str(state)
    try:
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(label, font=font)  # type: ignore[attr-defined]
    draw.text((x + cell_w - tw - 4, y + 4), label, fill=(255, 255, 255, 200), font=font)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_diffuse_texture(crop: CropConfig, output_dir: str | Path) -> Path:
    """Generate the RGBA diffuse atlas for *crop*."""
    size = crop.textureSize
    atlas = crop.atlasSize
    cell = size // atlas

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    base_color = FOLIAGE_COLORS.get(crop.foliageType, (120, 140, 60))
    total_cells = atlas * atlas
    total_states = crop.numGrowthStates

    for idx in range(total_cells):
        row = idx // atlas
        col = idx % atlas
        px = col * cell
        py = row * cell
        state = min(idx, total_states)
        _draw_foliage_cell(
            draw, px, py, cell, cell,
            state, total_states + 1,
            base_color, crop.foliageType,
        )

    # Watermark ───────────────────────────────────────────────────────────
    font = _get_font(max(12, size // 64))
    msg = "PLACEHOLDER – replace with actual artwork"
    try:
        bbox = draw.textbbox((0, 0), msg, font=font)
        tw = bbox[2] - bbox[0]
    except AttributeError:
        tw, _ = draw.textsize(msg, font=font)  # type: ignore[attr-defined]
    draw.text(((size - tw) // 2, size // 2 - 10), msg, fill=(255, 50, 50, 180), font=font)

    out = ensure_dir(output_dir)
    dest = out / f"{crop.name}_DIFFUSE.png"
    img.save(dest)
    return dest


def generate_normal_texture(crop: CropConfig, output_dir: str | Path) -> Path:
    """Generate a flat (pointing-up) RGB normal map atlas for *crop*."""
    size = crop.textureSize
    # Flat normal: R=128 G=128 B=255 (tangent space, no deflection)
    img = Image.new("RGB", (size, size), (128, 128, 255))
    draw = ImageDraw.Draw(img)

    atlas = crop.atlasSize
    cell = size // atlas
    # Draw cell borders so modders can see the atlas grid
    for i in range(atlas + 1):
        draw.line([(i * cell, 0), (i * cell, size)], fill=(100, 100, 200), width=1)
        draw.line([(0, i * cell), (size, i * cell)], fill=(100, 100, 200), width=1)

    out = ensure_dir(output_dir)
    dest = out / f"{crop.name}_NORMAL.png"
    img.save(dest)
    return dest


def generate_roughness_texture(crop: CropConfig, output_dir: str | Path) -> Path:
    """Generate a grayscale roughness atlas for *crop*."""
    size = crop.textureSize
    atlas = crop.atlasSize
    cell = size // atlas

    img = Image.new("L", (size, size), 180)
    draw = ImageDraw.Draw(img)

    for row in range(atlas):
        for col in range(atlas):
            state = row * atlas + col
            progress = state / max(crop.numGrowthStates, 1)
            # Younger growth = rougher (lighter); mature = smoother (darker)
            roughness = int(220 - 80 * progress)
            px, py = col * cell, row * cell
            draw.rectangle([px + 1, py + 1, px + cell - 2, py + cell - 2], fill=roughness)

    out = ensure_dir(output_dir)
    dest = out / f"{crop.name}_ROUGHNESS.png"
    img.save(dest)
    return dest


def generate_icon(crop: CropConfig, output_dir: str | Path, size: int = 128) -> Path:
    """Generate a simple 128×128 RGBA minimap / UI icon for *crop*."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    base_color = FOLIAGE_COLORS.get(crop.foliageType, (120, 140, 60))

    # Background circle
    draw.ellipse([4, 4, size - 4, size - 4], fill=(*base_color, 220),
                 outline=(50, 50, 50, 255), width=3)

    # Simple plant silhouette
    cx = size // 2
    stem_top = size // 6
    stem_bot = size * 5 // 6
    draw.line([(cx, stem_bot), (cx, stem_top + size // 8)], fill=(80, 80, 80, 255), width=4)
    draw.ellipse([cx - size // 6, stem_top - size // 8,
                  cx + size // 6, stem_top + size // 4],
                 fill=(50, 50, 50, 255))

    # Crop name label
    font = _get_font(max(10, size // 10))
    label = crop.name[:8]
    try:
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(label, font=font)  # type: ignore[attr-defined]
    draw.text(((size - tw) // 2, stem_bot - th - 4), label,
              fill=(255, 255, 255, 230), font=font)

    out = ensure_dir(output_dir)
    dest = out / f"icon_fruitType_{crop.name}.png"
    img.save(dest)
    return dest


def generate_all_textures(crop: CropConfig, output_dir: str | Path) -> dict[str, Path]:
    """Generate all placeholder textures for *crop*.

    Returns a dict mapping texture role → file path.
    """
    return {
        "diffuse": generate_diffuse_texture(crop, output_dir),
        "normal": generate_normal_texture(crop, output_dir),
        "roughness": generate_roughness_texture(crop, output_dir),
        "icon": generate_icon(crop, output_dir),
    }
