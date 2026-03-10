"""Tests for FS25 crop calendar and XML generation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.utils import (
    CropConfig,
    GrowthCycle,
    FS25_DEFAULT_CROPS,
    CROP_PRESETS,
    MONTH_ABBR,
    sanitize_name,
)
from src.xml_generator import (
    build_growth_xml,
    build_fruit_type_xml,
    build_maps_growth_xml,
    write_crop_files,
)
from src.crop_calendar import (
    generate_calendar_html,
    _crops_from_payload,
    _build_default_crops_payload,
    _month_class,
    _is_dormant,
)


# ---------------------------------------------------------------------------
# utils.py
# ---------------------------------------------------------------------------

class TestGrowthCycle:
    def test_growing_months_simple(self):
        """Months between sow and harvest (no wrap) are growing months."""
        c = GrowthCycle(seed_months=[3], harvest_months=[8])
        grow = c.growing_months()
        assert 4 in grow and 7 in grow
        assert 3 not in grow and 8 not in grow

    def test_growing_months_wraparound(self):
        """Fall sowing (Sep) → summer harvest (Jul): growing wraps around Jan."""
        c = GrowthCycle(seed_months=[9], harvest_months=[7])
        grow = c.growing_months()
        assert 10 in grow  # Oct after sowing
        assert 1 in grow   # Jan wrap-around
        assert 6 in grow   # Jun before harvest
        assert 9 not in grow and 7 not in grow

    def test_growing_months_empty_if_no_seed(self):
        c = GrowthCycle(harvest_months=[8])
        assert c.growing_months() == []

    def test_to_dict_roundtrip(self):
        c = GrowthCycle(seed_months=[3, 4], harvest_months=[8, 9],
                        first_dormant_month=11, last_dormant_month=2)
        d = c.to_dict()
        c2 = GrowthCycle.from_dict(d)
        assert c2.seed_months == [3, 4]
        assert c2.first_dormant_month == 11


class TestCropConfig:
    def test_apply_preset(self):
        crop = CropConfig(name="test", title="Test", preset="grain")
        crop.apply_preset()
        assert crop.windParameters == "wheat"
        assert crop.numGrowthStates == 8

    def test_apply_preset_row_crop(self):
        crop = CropConfig(name="test", title="Test", preset="row_crop")
        crop.apply_preset()
        assert crop.windParameters == "corn"
        assert crop.swathWidth == 6

    def test_to_dict_includes_cycles(self):
        crop = CropConfig(name="w", title="Wheat")
        crop.cycles = [GrowthCycle(seed_months=[9], harvest_months=[7])]
        d = crop.to_dict()
        assert len(d["cycles"]) == 1
        assert d["cycles"][0]["seed_months"] == [9]

    def test_from_dict_roundtrip(self):
        original = CropConfig(name="canola", title="Canola", preset="oilseed")
        original.cycles = [GrowthCycle(seed_months=[8], harvest_months=[7],
                                       first_dormant_month=11, last_dormant_month=2)]
        d = original.to_dict()
        restored = CropConfig.from_dict(d)
        assert restored.name == "canola"
        assert len(restored.cycles) == 1
        assert restored.cycles[0].first_dormant_month == 11

    def test_to_json_and_from_json(self, tmp_path):
        crop = CropConfig(name="rye", title="Rye", preset="grain")
        crop.cycles = [GrowthCycle(seed_months=[9], harvest_months=[7])]
        path = tmp_path / "rye.json"
        crop.to_json(path)
        loaded = CropConfig.from_json(path)
        assert loaded.name == "rye"
        assert loaded.cycles[0].seed_months == [9]


class TestFs25DefaultCrops:
    def test_all_defaults_have_required_keys(self):
        for name, info in FS25_DEFAULT_CROPS.items():
            assert "title" in info, f"{name} missing title"
            assert "preset" in info, f"{name} missing preset"
            assert "cycles" in info, f"{name} missing cycles"
            assert info["preset"] in CROP_PRESETS, f"{name} has unknown preset"

    def test_each_crop_has_at_least_one_cycle(self):
        for name, info in FS25_DEFAULT_CROPS.items():
            assert len(info["cycles"]) >= 1, f"{name} has no cycles"

    def test_wheat_has_two_cycles(self):
        assert len(FS25_DEFAULT_CROPS["wheat"]["cycles"]) == 2

    def test_seed_months_in_range(self):
        for name, info in FS25_DEFAULT_CROPS.items():
            for cyc in info["cycles"]:
                for m in cyc["seed_months"]:
                    assert 1 <= m <= 12, f"{name}: seed month {m} out of range"

    def test_harvest_months_in_range(self):
        for name, info in FS25_DEFAULT_CROPS.items():
            for cyc in info["cycles"]:
                for m in cyc["harvest_months"]:
                    assert 1 <= m <= 12, f"{name}: harvest month {m} out of range"


class TestSanitizeName:
    def test_spaces_become_underscores(self):
        assert sanitize_name("My Crop") == "my_crop"

    def test_special_chars_removed(self):
        assert sanitize_name("crop-1!") == "crop_1_"

    def test_already_clean(self):
        assert sanitize_name("wheat") == "wheat"


# ---------------------------------------------------------------------------
# xml_generator.py
# ---------------------------------------------------------------------------

def _make_wheat() -> CropConfig:
    info = FS25_DEFAULT_CROPS["wheat"]
    c = CropConfig(name="wheat", title="Wheat", preset=info["preset"])
    c.apply_preset()
    c.cycles = [GrowthCycle(**cyc) for cyc in info["cycles"]]
    return c


class TestBuildGrowthXml:
    def test_contains_cycle_elements(self):
        xml = build_growth_xml(_make_wheat())
        assert "<cycle" in xml
        assert 'index="1"' in xml
        assert 'index="2"' in xml

    def test_contains_seed_months(self):
        xml = build_growth_xml(_make_wheat())
        assert "<seedMonth>9</seedMonth>" in xml
        assert "<seedMonth>10</seedMonth>" in xml

    def test_contains_harvest_months(self):
        xml = build_growth_xml(_make_wheat())
        assert "<harvestMonth>7</harvestMonth>" in xml

    def test_dormant_months_present(self):
        xml = build_growth_xml(_make_wheat())
        assert "<firstDormantMonth>11</firstDormantMonth>" in xml
        assert "<lastDormantMonth>2</lastDormantMonth>" in xml

    def test_no_dormant_if_zero(self):
        c = CropConfig(name="corn", title="Corn")
        c.cycles = [GrowthCycle(seed_months=[4], harvest_months=[10],
                                first_dormant_month=0, last_dormant_month=0)]
        xml = build_growth_xml(c)
        assert "firstDormantMonth" not in xml

    def test_empty_cycles_produces_empty_cycle_element(self):
        c = CropConfig(name="x", title="X")
        xml = build_growth_xml(c)
        assert "<cycle" in xml


class TestBuildFruitTypeXml:
    def test_starts_with_xml_declaration(self):
        xml = build_fruit_type_xml(_make_wheat())
        assert xml.startswith('<?xml version="1.0"')

    def test_contains_fruit_type_element(self):
        xml = build_fruit_type_xml(_make_wheat())
        assert '<fruitType name="WHEAT"' in xml

    def test_contains_growth_element(self):
        xml = build_fruit_type_xml(_make_wheat())
        assert "<growth>" in xml

    def test_contains_texture_references(self):
        xml = build_fruit_type_xml(_make_wheat())
        assert "wheat_DIFFUSE.png" in xml


class TestBuildMapsGrowthXml:
    def test_contains_all_crops(self):
        crops = [_make_wheat()]
        info = FS25_DEFAULT_CROPS["corn"]
        corn = CropConfig(name="corn", title="Corn", preset=info["preset"])
        corn.apply_preset()
        corn.cycles = [GrowthCycle(**c) for c in info["cycles"]]
        crops.append(corn)

        xml = build_maps_growth_xml(crops)
        assert "<fruits>" in xml
        assert '<fruit name="WHEAT">' in xml
        assert '<fruit name="CORN">' in xml

    def test_starts_with_xml_declaration(self):
        xml = build_maps_growth_xml([_make_wheat()])
        assert xml.startswith('<?xml version="1.0"')


class TestWriteCropFiles:
    def test_writes_expected_files(self, tmp_path):
        crop = _make_wheat()
        paths = write_crop_files(crop, tmp_path)
        assert "fruitType" in paths
        assert "growth" in paths
        assert "modDesc" in paths
        for p in paths.values():
            assert p.exists()
            assert p.stat().st_size > 0

    def test_fruit_type_xml_is_valid(self, tmp_path):
        crop = _make_wheat()
        paths = write_crop_files(crop, tmp_path)
        content = paths["fruitType"].read_text()
        assert "WHEAT" in content
        assert "<growth>" in content

    def test_growth_xml_is_valid(self, tmp_path):
        crop = _make_wheat()
        paths = write_crop_files(crop, tmp_path)
        content = paths["growth"].read_text()
        assert "<growth>" in content
        assert "<seedMonth>" in content


# ---------------------------------------------------------------------------
# crop_calendar.py
# ---------------------------------------------------------------------------

class TestIsDormant:
    def test_within_range(self):
        c = GrowthCycle(first_dormant_month=11, last_dormant_month=2)
        assert _is_dormant(11, c)
        assert _is_dormant(12, c)
        assert _is_dormant(1, c)
        assert _is_dormant(2, c)

    def test_outside_range(self):
        c = GrowthCycle(first_dormant_month=11, last_dormant_month=2)
        assert not _is_dormant(3, c)
        assert not _is_dormant(10, c)

    def test_no_dormancy(self):
        c = GrowthCycle(first_dormant_month=0, last_dormant_month=0)
        assert not _is_dormant(1, c)

    def test_non_wrapping_range(self):
        c = GrowthCycle(first_dormant_month=6, last_dormant_month=8)
        assert _is_dormant(7, c)
        assert not _is_dormant(5, c)


class TestMonthClass:
    def test_harvest_month_returns_harvest(self):
        c = GrowthCycle(seed_months=[3], harvest_months=[8])
        assert _month_class(8, c) == "harvest"

    def test_sow_month_returns_sow(self):
        c = GrowthCycle(seed_months=[3], harvest_months=[8])
        assert _month_class(3, c) == "sow"

    def test_dormant_month_returns_dormant(self):
        c = GrowthCycle(seed_months=[9], harvest_months=[7],
                        first_dormant_month=11, last_dormant_month=2)
        assert _month_class(12, c) == "dormant"

    def test_idle_month(self):
        # Aug is between Jul harvest and Sep sow — not sow, harvest, dormant or grow
        c = GrowthCycle(seed_months=[9], harvest_months=[7])
        assert _month_class(8, c) == "idle"


class TestGenerateCalendarHtml:
    def test_creates_html_file(self, tmp_path):
        defaults = _build_default_crops_payload()
        crops = _crops_from_payload({"crops": defaults})
        dest = generate_calendar_html(crops, tmp_path)
        assert dest.exists()
        assert dest.suffix == ".html"

    def test_html_contains_all_crops(self, tmp_path):
        defaults = _build_default_crops_payload()
        crops = _crops_from_payload({"crops": defaults})
        dest = generate_calendar_html(crops, tmp_path)
        html = dest.read_text()
        assert "Wheat" in html
        assert "Corn" in html
        assert "Canola" in html

    def test_html_contains_legend(self, tmp_path):
        crops = _crops_from_payload({"crops": _build_default_crops_payload()[:2]})
        dest = generate_calendar_html(crops, tmp_path)
        html = dest.read_text()
        assert "Sow" in html
        assert "Harvest" in html

    def test_empty_crops_produces_valid_html(self, tmp_path):
        dest = generate_calendar_html([], tmp_path)
        html = dest.read_text()
        assert "<!DOCTYPE html>" in html
        assert "No crop data" in html


class TestCropsFromPayload:
    def test_builds_crop_list(self):
        payload = {"crops": [
            {"name": "wheat", "title": "Wheat", "preset": "grain",
             "cycles": [{"seed_months": [9], "harvest_months": [7],
                         "first_dormant_month": 11, "last_dormant_month": 2}]},
        ]}
        crops = _crops_from_payload(payload)
        assert len(crops) == 1
        assert crops[0].name == "wheat"
        assert crops[0].cycles[0].seed_months == [9]

    def test_empty_payload(self):
        assert _crops_from_payload({}) == []

    def test_applies_preset(self):
        payload = {"crops": [
            {"name": "corn", "title": "Corn", "preset": "row_crop", "cycles": []}
        ]}
        crops = _crops_from_payload(payload)
        assert crops[0].windParameters == "corn"


class TestBuildDefaultCropsPayload:
    def test_returns_all_defaults(self):
        defaults = _build_default_crops_payload()
        assert len(defaults) == len(FS25_DEFAULT_CROPS)

    def test_each_entry_has_required_fields(self):
        for entry in _build_default_crops_payload():
            assert "name" in entry
            assert "title" in entry
            assert "preset" in entry
            assert "cycles" in entry
