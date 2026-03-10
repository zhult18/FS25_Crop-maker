"""Detect the crop type from a natural-language prompt.

The detector uses a keyword/scoring approach so no external LLM or network
connection is needed.  It returns the best-matching crop from a built-in
database of ~35 real-world FS25-relevant crops together with a confidence
score and a ready-to-use :class:`~src.utils.CropConfig`.

Typical usage
-------------
    from src.crop_detector import detect_crop

    match = detect_crop("I want to create a sunflower crop")
    # match.crop_name  → "sunflower"
    # match.preset     → "oilseed"
    # match.confidence → 0.95
    # match.config     → CropConfig(...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .utils import CROP_PRESETS, CropConfig, sanitize_name

# ---------------------------------------------------------------------------
# Crop database
# Each entry:
#   name        – canonical identifier (will be used as the CropConfig name)
#   title       – human-readable display name
#   preset      – one of the keys in CROP_PRESETS
#   keywords    – list of strings (matched case-insensitively against the prompt)
#   description – one-liner shown in the UI
# ---------------------------------------------------------------------------

CROP_DATABASE: list[dict] = [
    # ── Grain crops ──────────────────────────────────────────────────────
    {
        "name": "wheat",
        "title": "Wheat",
        "preset": "grain",
        "keywords": [
            "wheat", "winter wheat", "spring wheat", "hard wheat", "soft wheat",
            "durum", "triticum", "bread wheat", "common wheat",
        ],
        "description": "Staple cereal grain, one of the most widely grown crops worldwide.",
    },
    {
        "name": "barley",
        "title": "Barley",
        "preset": "grain",
        "keywords": [
            "barley", "malt barley", "malting barley", "beer barley",
            "winter barley", "spring barley", "hordeum",
        ],
        "description": "Cereal grain used for malting, animal feed, and food production.",
    },
    {
        "name": "oat",
        "title": "Oat",
        "preset": "grain",
        "keywords": ["oat", "oats", "avena", "oatmeal", "rolled oat"],
        "description": "Nutritious cereal grain popular as food and animal feed.",
    },
    {
        "name": "rye",
        "title": "Rye",
        "preset": "grain",
        "keywords": ["rye", "winter rye", "secale", "rye grain"],
        "description": "Hardy cereal grain that thrives in cold climates.",
    },
    {
        "name": "triticale",
        "title": "Triticale",
        "preset": "grain",
        "keywords": ["triticale", "wheat rye hybrid", "rye wheat"],
        "description": "Hybrid of wheat and rye, high-yielding forage or grain crop.",
    },
    {
        "name": "sorghum",
        "title": "Sorghum",
        "preset": "row_crop",
        "keywords": [
            "sorghum", "grain sorghum", "milo", "sweet sorghum", "jowar",
        ],
        "description": "Drought-tolerant cereal grain grown in warm, dry climates.",
    },
    {
        "name": "millet",
        "title": "Millet",
        "preset": "grain",
        "keywords": ["millet", "pearl millet", "foxtail millet", "finger millet", "proso millet"],
        "description": "Small-seeded cereal crop suited to dry, low-fertility soils.",
    },
    {
        "name": "amaranth",
        "title": "Amaranth",
        "preset": "grain",
        "keywords": ["amaranth", "grain amaranth", "pseudocereal"],
        "description": "Ancient pseudocereal with vibrant seed heads, high in protein.",
    },
    # ── Row crops ────────────────────────────────────────────────────────
    {
        "name": "corn",
        "title": "Corn",
        "preset": "row_crop",
        "keywords": [
            "corn", "maize", "sweetcorn", "sweet corn", "zea mays",
            "field corn", "dent corn", "flint corn", "popcorn",
        ],
        "description": "Tall row crop, the most produced grain worldwide.",
    },
    {
        "name": "sugarcane",
        "title": "Sugar Cane",
        "preset": "row_crop",
        "keywords": ["sugarcane", "sugar cane", "cane", "saccharum"],
        "description": "Tall perennial grass grown in tropical regions for sugar.",
    },
    # ── Root / tuber crops ───────────────────────────────────────────────
    {
        "name": "potato",
        "title": "Potato",
        "preset": "root_crop",
        "keywords": [
            "potato", "potatoes", "solanum tuberosum", "spud", "spuds",
            "russet", "yukon gold", "red potato",
        ],
        "description": "Starchy tuber, one of the world's most important food crops.",
    },
    {
        "name": "sugarbeet",
        "title": "Sugar Beet",
        "preset": "root_crop",
        "keywords": [
            "sugarbeet", "sugar beet", "beet", "beetroot", "beta vulgaris",
            "fodder beet", "mangel",
        ],
        "description": "Root crop grown for its sucrose-rich storage root.",
    },
    {
        "name": "carrot",
        "title": "Carrot",
        "preset": "root_crop",
        "keywords": ["carrot", "carrots", "daucus carota", "baby carrot"],
        "description": "Root vegetable with characteristic orange taproot.",
    },
    {
        "name": "turnip",
        "title": "Turnip",
        "preset": "root_crop",
        "keywords": ["turnip", "turnips", "brassica rapa", "white turnip"],
        "description": "White-fleshed root vegetable used as food and livestock fodder.",
    },
    {
        "name": "parsnip",
        "title": "Parsnip",
        "preset": "root_crop",
        "keywords": ["parsnip", "parsnips", "pastinaca sativa"],
        "description": "Sweet, nutty root vegetable similar to the carrot.",
    },
    {
        "name": "radish",
        "title": "Radish",
        "preset": "root_crop",
        "keywords": ["radish", "radishes", "raphanus", "daikon"],
        "description": "Fast-growing root vegetable also used as a cover crop.",
    },
    # ── Oilseed crops ────────────────────────────────────────────────────
    {
        "name": "canola",
        "title": "Canola",
        "preset": "oilseed",
        "keywords": [
            "canola", "rapeseed", "rape", "oilseed rape", "brassica napus",
            "colza", "raps",
        ],
        "description": "Oilseed crop with bright yellow flowers; yields cooking oil and biodiesel.",
    },
    {
        "name": "sunflower",
        "title": "Sunflower",
        "preset": "oilseed",
        "keywords": [
            "sunflower", "sunflowers", "helianthus", "oilseed sunflower",
        ],
        "description": "Tall oilseed crop with distinctive large yellow flower heads.",
    },
    {
        "name": "flax",
        "title": "Flax",
        "preset": "oilseed",
        "keywords": ["flax", "linseed", "linum usitatissimum", "flaxseed"],
        "description": "Dual-purpose crop producing linseed oil and natural fibre.",
    },
    {
        "name": "hemp",
        "title": "Hemp",
        "preset": "oilseed",
        "keywords": ["hemp", "industrial hemp", "cannabis sativa", "fibre hemp"],
        "description": "Tall fibre and seed crop with many industrial uses.",
    },
    {
        "name": "safflower",
        "title": "Safflower",
        "preset": "oilseed",
        "keywords": ["safflower", "carthamus tinctorius"],
        "description": "Drought-tolerant oilseed crop with spiny thistle-like heads.",
    },
    # ── Legume crops ─────────────────────────────────────────────────────
    {
        "name": "soybean",
        "title": "Soybean",
        "preset": "legume",
        "keywords": [
            "soybean", "soy bean", "soybeans", "soy", "glycine max",
            "soya", "soya bean",
        ],
        "description": "High-protein legume used in food, feed, and oil production.",
    },
    {
        "name": "pea",
        "title": "Pea",
        "preset": "legume",
        "keywords": [
            "pea", "peas", "pisum sativum", "field pea", "garden pea",
            "green pea",
        ],
        "description": "Cool-season legume grown for fresh pods, dried seeds, and fodder.",
    },
    {
        "name": "bean",
        "title": "Bean",
        "preset": "legume",
        "keywords": [
            "bean", "beans", "field bean", "faba bean", "fava bean",
            "broad bean", "vicia faba", "haricot bean",
        ],
        "description": "Legume with large seeds, grown for food and nitrogen fixation.",
    },
    {
        "name": "lentil",
        "title": "Lentil",
        "preset": "legume",
        "keywords": ["lentil", "lentils", "lens culinaris"],
        "description": "Small-seeded pulse crop used extensively in human nutrition.",
    },
    {
        "name": "chickpea",
        "title": "Chickpea",
        "preset": "legume",
        "keywords": ["chickpea", "chickpeas", "garbanzo", "cicer arietinum"],
        "description": "Drought-tolerant pulse crop, a major protein source worldwide.",
    },
    {
        "name": "lupin",
        "title": "Lupin",
        "preset": "legume",
        "keywords": ["lupin", "lupine", "lupins", "lupinus"],
        "description": "Hardy legume with tall flower spikes; used for fodder and food.",
    },
    # ── Grass / forage ───────────────────────────────────────────────────
    {
        "name": "grass",
        "title": "Grass",
        "preset": "grass",
        "keywords": ["grass", "lawn", "turf", "meadow grass", "pasture"],
        "description": "General grass / pasture mix for hay and grazing.",
    },
    {
        "name": "alfalfa",
        "title": "Alfalfa",
        "preset": "grass",
        "keywords": ["alfalfa", "lucerne", "medicago sativa"],
        "description": "High-protein perennial forage legume, cut multiple times per year.",
    },
    {
        "name": "clover",
        "title": "Clover",
        "preset": "grass",
        "keywords": [
            "clover", "red clover", "white clover", "trifolium",
            "crimson clover",
        ],
        "description": "Nitrogen-fixing forage crop often grown in grass mixtures.",
    },
    {
        "name": "ryegrass",
        "title": "Ryegrass",
        "preset": "grass",
        "keywords": [
            "ryegrass", "rye grass", "lolium", "perennial ryegrass",
            "italian ryegrass",
        ],
        "description": "High-yielding perennial or annual grass used for silage and grazing.",
    },
]

# ---------------------------------------------------------------------------
# Category keyword fallbacks (when no specific crop is matched)
# ---------------------------------------------------------------------------

_CATEGORY_HINTS: list[tuple[list[str], str]] = [
    (["grain", "cereal", "corn-like", "straw"], "grain"),
    (["row", "tall plant", "stalk"], "row_crop"),
    (["root", "tuber", "underground", "bulb", "beet"], "root_crop"),
    (["oil", "oilseed", "seed oil", "fat"], "oilseed"),
    (["legume", "pulse", "bean-like", "nitrogen", "pod"], "legume"),
    (["grass", "hay", "forage", "pasture", "silage"], "grass"),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CropMatch:
    """Result from :func:`detect_crop`."""

    crop_name: str
    title: str
    preset: str
    description: str
    confidence: float          # 0.0 – 1.0
    matched_keyword: str       # the keyword that triggered the match
    config: CropConfig = field(repr=False, default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = _make_config(self.crop_name, self.title, self.preset)

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.75:
            return "High"
        if self.confidence >= 0.5:
            return "Medium"
        return "Low"


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> str:
    """Lowercase and strip punctuation."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def _score_entry(tokens: str, entry: dict) -> tuple[float, str]:
    """Return (score 0-1, matched_keyword) for a database entry against tokens."""
    best_score = 0.0
    best_kw = ""
    for kw in entry["keywords"]:
        kw_clean = kw.lower()
        # Exact phrase match
        if kw_clean in tokens:
            # Longer keyword = more specific = higher score
            score = 0.7 + min(len(kw_clean) / 40, 0.3)
            if score > best_score:
                best_score = score
                best_kw = kw
        else:
            # Partial word overlap
            kw_words = set(kw_clean.split())
            tok_words = set(tokens.split())
            overlap = kw_words & tok_words
            if overlap:
                ratio = len(overlap) / len(kw_words)
                score = 0.4 * ratio
                if score > best_score:
                    best_score = score
                    best_kw = " + ".join(overlap)

    return best_score, best_kw


def _infer_name_from_prompt(prompt: str) -> str:
    """Try to extract a plausible single-word crop name from the prompt."""
    tokens = _tokenize(prompt).split()
    stop = {
        "create", "make", "generate", "build", "new", "crop", "type",
        "plant", "i", "want", "a", "an", "the", "my", "for", "mod",
        "fs25", "farming", "simulator", "add", "some", "please",
    }
    candidates = [t for t in tokens if t not in stop and len(t) > 2]
    return sanitize_name(candidates[0]) if candidates else "custom_crop"


def _make_config(name: str, title: str, preset: str) -> CropConfig:
    crop = CropConfig(name=sanitize_name(name), title=title, preset=preset)
    crop.apply_preset()
    return crop


def detect_crop(prompt: str) -> CropMatch:
    """Analyse *prompt* and return the best-matching :class:`CropMatch`.

    The detector scores every entry in :data:`CROP_DATABASE` and picks the
    highest-scoring one.  If nothing scores above a low threshold the
    category hints are used as a last resort.  A "custom crop" fallback
    is returned when everything else fails.
    """
    tokens = _tokenize(prompt)

    best_score = 0.0
    best_entry: Optional[dict] = None
    best_kw = ""

    for entry in CROP_DATABASE:
        score, kw = _score_entry(tokens, entry)
        if score > best_score:
            best_score = score
            best_entry = entry
            best_kw = kw

    # ── Good match found ──────────────────────────────────────────────────
    if best_score >= 0.4 and best_entry is not None:
        return CropMatch(
            crop_name=best_entry["name"],
            title=best_entry["title"],
            preset=best_entry["preset"],
            description=best_entry["description"],
            confidence=min(best_score, 1.0),
            matched_keyword=best_kw,
        )

    # ── Category fallback ─────────────────────────────────────────────────
    for hints, preset_name in _CATEGORY_HINTS:
        for hint in hints:
            if hint in tokens:
                inferred_name = _infer_name_from_prompt(prompt)
                return CropMatch(
                    crop_name=inferred_name,
                    title=inferred_name.replace("_", " ").capitalize(),
                    preset=preset_name,
                    description=f"Custom {preset_name.replace('_', ' ')} crop.",
                    confidence=0.35,
                    matched_keyword=hint,
                )

    # ── Unknown crop – use inferred name with grain defaults ──────────────
    inferred_name = _infer_name_from_prompt(prompt)
    return CropMatch(
        crop_name=inferred_name,
        title=inferred_name.replace("_", " ").capitalize(),
        preset="grain",
        description="Unrecognised crop; defaulting to grain preset. Edit the name and properties as needed.",
        confidence=0.1,
        matched_keyword="(none)",
    )


def list_known_crops() -> list[dict]:
    """Return the full crop database (name, title, preset, description)."""
    return [
        {"name": e["name"], "title": e["title"], "preset": e["preset"], "description": e["description"]}
        for e in CROP_DATABASE
    ]
