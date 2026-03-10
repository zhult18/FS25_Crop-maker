"""Shared constants, data structures and utility functions for FS25 Crop Maker."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

MONTH_ABBR = [m[:3] for m in MONTH_NAMES]

CLIMATE_ZONES = ["temperate", "continental", "dry", "tropical", "cold"]

# ---------------------------------------------------------------------------
# Standard FS25 base-game crops with default growth cycles
# Each entry: (display_name, preset, cycles)
# cycle keys: seed_months, harvest_months, first_dormant_month, last_dormant_month
# 0 = no dormancy; months are 1-12
# ---------------------------------------------------------------------------

FS25_DEFAULT_CROPS: dict[str, dict[str, Any]] = {
    "wheat": {
        "title": "Wheat",
        "preset": "grain",
        "cycles": [
            {
                "seed_months": [9, 10],
                "harvest_months": [7, 8],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
            {
                "seed_months": [3, 4],
                "harvest_months": [8, 9],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "barley": {
        "title": "Barley",
        "preset": "grain",
        "cycles": [
            {
                "seed_months": [9, 10],
                "harvest_months": [6, 7],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
            {
                "seed_months": [3, 4],
                "harvest_months": [7, 8],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "canola": {
        "title": "Canola / Rapeseed",
        "preset": "oilseed",
        "cycles": [
            {
                "seed_months": [8, 9],
                "harvest_months": [7, 8],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
        ],
    },
    "corn": {
        "title": "Corn / Maize",
        "preset": "row_crop",
        "cycles": [
            {
                "seed_months": [4, 5],
                "harvest_months": [10, 11],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "sunflower": {
        "title": "Sunflower",
        "preset": "oilseed",
        "cycles": [
            {
                "seed_months": [4, 5],
                "harvest_months": [9, 10],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "soybean": {
        "title": "Soybean",
        "preset": "legume",
        "cycles": [
            {
                "seed_months": [4, 5, 6],
                "harvest_months": [9, 10],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "potato": {
        "title": "Potato",
        "preset": "root_crop",
        "cycles": [
            {
                "seed_months": [3, 4, 5],
                "harvest_months": [9, 10],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "sugarbeet": {
        "title": "Sugar Beet",
        "preset": "root_crop",
        "cycles": [
            {
                "seed_months": [3, 4, 5],
                "harvest_months": [10, 11],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "grass": {
        "title": "Grass / Hay",
        "preset": "grass",
        "cycles": [
            {
                "seed_months": [3, 4, 5, 6, 7, 8],
                "harvest_months": [5, 6, 7, 8, 9],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
        ],
    },
    "oat": {
        "title": "Oat",
        "preset": "grain",
        "cycles": [
            {
                "seed_months": [9, 10],
                "harvest_months": [6, 7],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
            {
                "seed_months": [3, 4],
                "harvest_months": [8, 9],
                "first_dormant_month": 0,
                "last_dormant_month": 0,
            },
        ],
    },
    "rye": {
        "title": "Rye",
        "preset": "grain",
        "cycles": [
            {
                "seed_months": [8, 9, 10],
                "harvest_months": [7, 8],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
        ],
    },
    "triticale": {
        "title": "Triticale",
        "preset": "grain",
        "cycles": [
            {
                "seed_months": [9, 10],
                "harvest_months": [7, 8],
                "first_dormant_month": 11,
                "last_dormant_month": 2,
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# Crop presets
# ---------------------------------------------------------------------------

CROP_PRESETS: dict[str, dict[str, Any]] = {
    "grain": {
        "windParameters": "wheat",
        "maxCurvingAngle": "20",
        "maxCurvingFrequency": "0.14",
        "windRotation": "0.05",
        "densityBitmask": "15",
        "numGrowthStates": 8,
        "firstFruitStateIndex": 4,
        "minHarvestingGrowthState": 7,
        "maxHarvestingGrowthState": 8,
        "atlasSize": 4,
        "textureSize": 2048,
        "swathWidth": 3,
        "harvestFraction": "CHAFF",
        "foliageType": "grain",
    },
    "row_crop": {
        "windParameters": "corn",
        "maxCurvingAngle": "10",
        "maxCurvingFrequency": "0.08",
        "windRotation": "0.02",
        "densityBitmask": "15",
        "numGrowthStates": 8,
        "firstFruitStateIndex": 4,
        "minHarvestingGrowthState": 7,
        "maxHarvestingGrowthState": 8,
        "atlasSize": 4,
        "textureSize": 2048,
        "swathWidth": 6,
        "harvestFraction": "CHAFF",
        "foliageType": "row_crop",
    },
    "root_crop": {
        "windParameters": "wheat",
        "maxCurvingAngle": "15",
        "maxCurvingFrequency": "0.10",
        "windRotation": "0.03",
        "densityBitmask": "15",
        "numGrowthStates": 6,
        "firstFruitStateIndex": 3,
        "minHarvestingGrowthState": 5,
        "maxHarvestingGrowthState": 6,
        "atlasSize": 4,
        "textureSize": 1024,
        "swathWidth": 3,
        "harvestFraction": "FORAGE",
        "foliageType": "root_crop",
    },
    "oilseed": {
        "windParameters": "wheat",
        "maxCurvingAngle": "18",
        "maxCurvingFrequency": "0.12",
        "windRotation": "0.04",
        "densityBitmask": "15",
        "numGrowthStates": 8,
        "firstFruitStateIndex": 4,
        "minHarvestingGrowthState": 7,
        "maxHarvestingGrowthState": 8,
        "atlasSize": 4,
        "textureSize": 2048,
        "swathWidth": 3,
        "harvestFraction": "CHAFF",
        "foliageType": "oilseed",
    },
    "legume": {
        "windParameters": "wheat",
        "maxCurvingAngle": "12",
        "maxCurvingFrequency": "0.09",
        "windRotation": "0.03",
        "densityBitmask": "15",
        "numGrowthStates": 7,
        "firstFruitStateIndex": 3,
        "minHarvestingGrowthState": 6,
        "maxHarvestingGrowthState": 7,
        "atlasSize": 4,
        "textureSize": 2048,
        "swathWidth": 3,
        "harvestFraction": "CHAFF",
        "foliageType": "legume",
    },
    "grass": {
        "windParameters": "wheat",
        "maxCurvingAngle": "25",
        "maxCurvingFrequency": "0.18",
        "windRotation": "0.06",
        "densityBitmask": "15",
        "numGrowthStates": 5,
        "firstFruitStateIndex": 3,
        "minHarvestingGrowthState": 4,
        "maxHarvestingGrowthState": 5,
        "atlasSize": 4,
        "textureSize": 1024,
        "swathWidth": 4,
        "harvestFraction": "FORAGE",
        "foliageType": "grass",
    },
}

FOLIAGE_COLORS: dict[str, tuple[int, int, int]] = {
    "grain": (180, 160, 60),
    "row_crop": (60, 140, 50),
    "root_crop": (80, 160, 70),
    "oilseed": (200, 190, 40),
    "legume": (100, 150, 60),
    "grass": (60, 180, 70),
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GrowthCycle:
    """A single planting–harvest cycle for one crop.

    Months are 1-12.  ``first_dormant_month`` / ``last_dormant_month`` = 0
    means no dormancy for this cycle.
    """

    seed_months: list[int] = field(default_factory=list)
    harvest_months: list[int] = field(default_factory=list)
    first_dormant_month: int = 0
    last_dormant_month: int = 0

    # Derived helpers --------------------------------------------------
    def growing_months(self) -> list[int]:
        """Return months that are neither seed nor harvest months but between them."""
        if not self.seed_months or not self.harvest_months:
            return []
        earliest_seed = min(self.seed_months)
        latest_harvest = max(self.harvest_months)
        # Handle wrap-around (e.g. fall sowing → summer harvest)
        if latest_harvest >= earliest_seed:
            return [
                m for m in range(1, 13)
                if earliest_seed < m < latest_harvest
                and m not in self.seed_months
                and m not in self.harvest_months
            ]
        # Wrap-around: seed in autumn, harvest in summer
        grow = []
        for m in range(1, 13):
            after_seed = m > earliest_seed or m < latest_harvest
            if after_seed and m not in self.seed_months and m not in self.harvest_months:
                grow.append(m)
        return grow

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GrowthCycle":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CropConfig:
    """Complete configuration for a single FS25 crop type."""

    name: str
    title: str
    preset: str = "grain"
    # Wind / physics
    windParameters: str = "wheat"
    maxCurvingAngle: str = "20"
    maxCurvingFrequency: str = "0.14"
    windRotation: str = "0.05"
    densityBitmask: str = "15"
    # Growth
    numGrowthStates: int = 8
    firstFruitStateIndex: int = 4
    minHarvestingGrowthState: int = 7
    maxHarvestingGrowthState: int = 8
    # Texture atlas
    atlasSize: int = 4
    textureSize: int = 2048
    # Harvest
    swathWidth: int = 3
    harvestFraction: str = "CHAFF"
    foliageType: str = "grain"
    # Growth cycles (FS25 style)
    cycles: list[GrowthCycle] = field(default_factory=list)

    # -----------------------------------------------------------------------
    def apply_preset(self) -> None:
        """Overwrite fields from the chosen preset."""
        p = CROP_PRESETS.get(self.preset, CROP_PRESETS["grain"])
        for key, value in p.items():
            if hasattr(self, key):
                setattr(self, key, value)

    # -----------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CropConfig":
        data = dict(data)
        cycles_raw = data.pop("cycles", [])
        obj = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        obj.cycles = [GrowthCycle.from_dict(c) for c in cycles_raw]
        return obj

    @classmethod
    def from_json(cls, path: str | Path) -> "CropConfig":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sanitize_name(name: str) -> str:
    """Return an identifier-safe version of *name* (lowercase, underscores)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
