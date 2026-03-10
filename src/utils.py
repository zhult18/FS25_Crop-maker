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
# Crop presets
# ---------------------------------------------------------------------------

# Wind parameter presets reference the FS25 base-game wind parameter groups.
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

# Colour used per preset type for placeholder texture tinting (RGB)
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
class CalendarEntry:
    """Growing-season data for one climate zone."""

    zone: str
    planting_months: list[int] = field(default_factory=list)   # 1-12
    growing_months: list[int] = field(default_factory=list)
    harvesting_months: list[int] = field(default_factory=list)


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
    # Foliage type (controls placeholder colours / shape)
    foliageType: str = "grain"
    # Calendar entries per zone
    calendar: list[CalendarEntry] = field(default_factory=list)

    # -----------------------------------------------------------------------
    def apply_preset(self) -> None:
        """Overwrite fields from the chosen preset (preserves name/title/calendar)."""
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
        calendar_raw = data.pop("calendar", [])
        obj = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        obj.calendar = [CalendarEntry(**c) for c in calendar_raw]
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
