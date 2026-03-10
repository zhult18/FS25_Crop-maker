"""FS25 XML generator.

Produces:
  * ``{name}.xml``               – fruitType definition
  * ``{name}_modDesc_entry.xml`` – snippet to paste into modDesc.xml
  * ``{name}_growth.xml``        – standalone growth-cycle XML (FS25 format)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .utils import CropConfig, GrowthCycle, MONTH_ABBR, ensure_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _indent(elem: ET.Element, level: int = 0) -> None:
    """Add pretty-print indentation to an ElementTree in-place."""
    pad = "\n" + "    " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = pad
        last_child = None
        for child in elem:
            _indent(child, level + 1)
            last_child = child
        if last_child is not None and (not last_child.tail or not last_child.tail.strip()):
            last_child.tail = pad
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = pad
    if not level:
        elem.tail = "\n"


def _xml_str(elem: ET.Element) -> str:
    _indent(elem)
    return ET.tostring(elem, encoding="unicode", xml_declaration=False)


# ---------------------------------------------------------------------------
# Growth-cycle XML (FS25 foliage format)
# ---------------------------------------------------------------------------

def _build_cycle_element(cycle: GrowthCycle, index: int) -> ET.Element:
    """Return a ``<cycle>`` XML element for one GrowthCycle."""
    cyc = ET.Element("cycle", {"index": str(index)})
    for m in cycle.seed_months:
        ET.SubElement(cyc, "seedMonth").text = str(m)
    for m in cycle.harvest_months:
        ET.SubElement(cyc, "harvestMonth").text = str(m)
    if cycle.first_dormant_month:
        ET.SubElement(cyc, "firstDormantMonth").text = str(cycle.first_dormant_month)
        ET.SubElement(cyc, "lastDormantMonth").text = str(cycle.last_dormant_month)
    return cyc


def build_growth_xml(crop: CropConfig) -> str:
    """Return the ``<growth>`` XML fragment for *crop*."""
    root = ET.Element("growth")
    if not crop.cycles:
        ET.SubElement(root, "cycle", {"index": "1"})
    else:
        for i, cycle in enumerate(crop.cycles, start=1):
            root.append(_build_cycle_element(cycle, i))
    return _xml_str(root)


# ---------------------------------------------------------------------------
# Fruit-type XML
# ---------------------------------------------------------------------------

def build_fruit_type_xml(crop: CropConfig) -> str:
    """Return a complete ``<fruitType>`` XML string for *crop*."""
    root = ET.Element("fruitType", {
        "name": crop.name.upper(),
        "title": f"$l10n_{crop.name}_title",
        "category": "CROP",
        "boughtFromShop": "false",
    })

    # ── harvest ──────────────────────────────────────────────────────────
    harvest = ET.SubElement(root, "harvest")
    ET.SubElement(harvest, "swath", {"width": str(crop.swathWidth)})

    # ── wind ─────────────────────────────────────────────────────────────
    ET.SubElement(root, "windParameters", {
        "useWindParameters": crop.windParameters,
        "maxCurvingAngle": crop.maxCurvingAngle,
        "maxCurvingFrequency": crop.maxCurvingFrequency,
        "windRotation": crop.windRotation,
    })

    # ── foliage ───────────────────────────────────────────────────────────
    foliage = ET.SubElement(root, "foliage", {
        "densityBitmask": crop.densityBitmask,
        "numGrowthStates": str(crop.numGrowthStates),
        "firstFruitStateIndex": str(crop.firstFruitStateIndex),
        "minHarvestingGrowthState": str(crop.minHarvestingGrowthState),
        "maxHarvestingGrowthState": str(crop.maxHarvestingGrowthState),
    })
    ET.SubElement(foliage, "foliageType", {"type": crop.foliageType})

    # ── texture atlas ─────────────────────────────────────────────────────
    textures = ET.SubElement(root, "textures")
    for suffix in ("DIFFUSE", "NORMAL", "ROUGHNESS"):
        ET.SubElement(textures, "texture", {
            "filename": f"textures/{crop.name}_{suffix}.png",
            "type": suffix,
        })

    # ── growth cycles ─────────────────────────────────────────────────────
    growth = ET.SubElement(root, "growth")
    if not crop.cycles:
        ET.SubElement(growth, "cycle", {"index": "1"})
    else:
        for i, cycle in enumerate(crop.cycles, start=1):
            growth.append(_build_cycle_element(cycle, i))

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _xml_str(root)


# ---------------------------------------------------------------------------
# modDesc entry XML
# ---------------------------------------------------------------------------

def build_mod_desc_entry(crop: CropConfig) -> str:
    """Return a ``<fruitType>`` snippet for modDesc.xml."""
    root = ET.Element("fruitType", {
        "name": crop.name.upper(),
        "filename": f"xml/{crop.name}.xml",
    })
    return _xml_str(root)


# ---------------------------------------------------------------------------
# maps_growth.xml (multi-crop project export)
# ---------------------------------------------------------------------------

def build_maps_growth_xml(crops: list[CropConfig]) -> str:
    """Return a ``maps_growth.xml`` style document for all *crops*.

    This matches the FS25 per-crop foliage XML calendar convention, with one
    ``<fruit>`` element per crop containing its ``<cycle>`` children.
    """
    root = ET.Element("fruits")
    for crop in crops:
        fruit = ET.SubElement(root, "fruit", {"name": crop.name.upper()})
        if not crop.cycles:
            ET.SubElement(fruit, "cycle", {"index": "1"})
        else:
            for i, cycle in enumerate(crop.cycles, start=1):
                fruit.append(_build_cycle_element(cycle, i))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _xml_str(root)


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def write_crop_files(crop: CropConfig, output_dir: str | Path) -> dict[str, Path]:
    """Write all XML files for *crop* to *output_dir*. Returns paths dict."""
    out = ensure_dir(Path(output_dir) / crop.name)
    xml_dir = ensure_dir(out / "xml")

    paths: dict[str, Path] = {}

    fruit_path = xml_dir / f"{crop.name}.xml"
    fruit_path.write_text(build_fruit_type_xml(crop), encoding="utf-8")
    paths["fruitType"] = fruit_path

    mod_path = xml_dir / f"{crop.name}_modDesc_entry.xml"
    mod_path.write_text(build_mod_desc_entry(crop), encoding="utf-8")
    paths["modDesc"] = mod_path

    growth_path = xml_dir / f"{crop.name}_growth.xml"
    growth_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + build_growth_xml(crop),
        encoding="utf-8",
    )
    paths["growth"] = growth_path

    return paths
