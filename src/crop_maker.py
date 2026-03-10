"""FS25 Crop Maker – main CLI tool.

Generates all files needed to add a new crop type to a Farming Simulator 25 mod:

  * ``<cropName>.xml``              – fruit-type XML definition
  * ``<cropName>_modDesc_entry.xml``– snippet to paste into modDesc.xml
  * ``textures/<cropName>_DIFFUSE.png``   – RGBA foliage atlas (placeholder)
  * ``textures/<cropName>_NORMAL.png``    – normal-map atlas (placeholder)
  * ``textures/<cropName>_ROUGHNESS.png`` – roughness atlas (placeholder)
  * ``textures/icon_fruitType_<cropName>.png`` – minimap icon (placeholder)
  * ``<cropName>_config.json``      – saved configuration for re-use

Usage examples
--------------
    # Interactive wizard
    python -m src.crop_maker

    # From a saved config
    python -m src.crop_maker --config examples/wheat_config.json --output ./output

    # Fully non-interactive
    python -m src.crop_maker --name wheat --title Wheat --preset grain --output ./output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .utils import CROP_PRESETS, CropConfig, ensure_dir, sanitize_name
from .xml_generator import generate_fruit_type_xml, generate_mod_desc_entry
from .texture_generator import generate_all_textures
from .crop_calendar import generate_calendar_html


# ---------------------------------------------------------------------------
# Wizard helpers
# ---------------------------------------------------------------------------


def _input(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val if val else default


def _run_wizard() -> CropConfig:
    print("\n╔══════════════════════════════════════╗")
    print("║  FS25 Crop Maker  –  Setup Wizard   ║")
    print("╚══════════════════════════════════════╝\n")

    name = sanitize_name(_input("Crop identifier (e.g. myCrop)", "myCrop"))
    title = _input("Crop display title", name.replace("_", " ").capitalize())

    presets = list(CROP_PRESETS.keys())
    print(f"\nAvailable presets: {', '.join(presets)}")
    preset = _input("Preset", "grain")
    if preset not in CROP_PRESETS:
        print(f"  ⚠  Unknown preset '{preset}', defaulting to 'grain'.")
        preset = "grain"

    crop = CropConfig(name=name, title=title, preset=preset)
    crop.apply_preset()
    return crop


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run(crop: CropConfig, output_dir: str | Path, *, verbose: bool = True) -> dict[str, Path]:
    """Generate all FS25 crop files for *crop* inside *output_dir*.

    Returns a mapping of role → generated file path.
    """
    base = ensure_dir(Path(output_dir) / crop.name)
    tex_dir = ensure_dir(base / "textures")

    generated: dict[str, Path] = {}

    # XML files
    generated["fruit_type_xml"] = generate_fruit_type_xml(crop, base)
    generated["mod_desc_entry"] = generate_mod_desc_entry(crop, base)

    # Textures
    textures = generate_all_textures(crop, tex_dir)
    generated.update(textures)

    # Calendar HTML (only if calendar data is present)
    if crop.calendar:
        generated["calendar_html"] = generate_calendar_html(crop, base)

    # Save config JSON for later re-use
    cfg_path = base / f"{crop.name}_config.json"
    crop.to_json(cfg_path)
    generated["config_json"] = cfg_path

    if verbose:
        print(f"\n✅  Generated files for '{crop.name}':")
        for role, path in generated.items():
            print(f"     {role:<20} → {path}")
        print()

    return generated


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> None:  # noqa: UP007
    parser = argparse.ArgumentParser(
        prog="crop_maker",
        description="FS25 Crop Maker – generate all textures and XML for a new crop type",
    )
    parser.add_argument("--name",   help="Crop identifier (e.g. myCrop)")
    parser.add_argument("--title",  help="Crop display title (e.g. 'My Crop')")
    parser.add_argument(
        "--preset",
        choices=list(CROP_PRESETS.keys()),
        default="grain",
        help="Crop preset (default: grain)",
    )
    parser.add_argument(
        "--config",
        help="Path to an existing crop JSON config (skips wizard)",
    )
    parser.add_argument(
        "--output", default="./output",
        help="Output directory (default: ./output)",
    )
    args = parser.parse_args(argv)

    if args.config:
        crop = CropConfig.from_json(args.config)
    elif args.name:
        name = sanitize_name(args.name)
        title = args.title or name.replace("_", " ").capitalize()
        crop = CropConfig(name=name, title=title, preset=args.preset)
        crop.apply_preset()
    else:
        crop = _run_wizard()

    run(crop, args.output)


if __name__ == "__main__":
    main()
