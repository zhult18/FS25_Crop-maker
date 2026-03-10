# FS25 Crop Maker

A toolkit for Farming Simulator 25 modders: design custom crop growing calendars visually and export all required FS25-compatible XML files.

## Features

### 🗓 Crop Calendar Editor (`python -m src.crop_calendar`, port 8080)

- **FS25-style multi-crop calendar** — all crops shown as rows, 12 months as columns; colour-coded **Sow / Grow / Harvest / Dormant**
- **Load FS25 Defaults** — pre-loads all 12 standard FS25 crops (wheat, barley, canola, corn, sunflower, soybean, potato, sugar beet, grass, oat, rye, triticale) with correct real-world schedules
- **Multi-cycle support** — define separate spring and autumn sowing windows for the same crop
- **Dormancy** — set `firstDormantMonth` / `lastDormantMonth` (wrap-around supported, e.g. Nov → Feb)
- **Export FS25 XML** — generates `<fruitType>` XML with proper `<cycle>` elements (`<seedMonth>`, `<harvestMonth>`, `<firstDormantMonth>`, `<lastDormantMonth>`)
- **Export maps_growth.xml** — combined `<fruits>` document covering every crop in the project
- **Export Calendar HTML** — standalone colour-coded reference sheet
- **Save / Load JSON** — persist your project and reload it later

![Calendar editor screenshot](https://github.com/user-attachments/assets/f4adeae4-43ca-45df-9d1c-2f722fa0373d)

### Generated XML (FS25 format)

```xml
<!-- wheat_growth.xml -->
<growth>
    <cycle index="1">
        <seedMonth>9</seedMonth>
        <seedMonth>10</seedMonth>
        <harvestMonth>7</harvestMonth>
        <harvestMonth>8</harvestMonth>
        <firstDormantMonth>11</firstDormantMonth>
        <lastDormantMonth>2</lastDormantMonth>
    </cycle>
    <cycle index="2">
        <seedMonth>3</seedMonth>
        <seedMonth>4</seedMonth>
        <harvestMonth>8</harvestMonth>
        <harvestMonth>9</harvestMonth>
    </cycle>
</growth>
```

### Exported calendar (all 12 FS25 base crops)

![Crop calendar export](https://github.com/user-attachments/assets/674dce44-8b79-4ae8-91e3-e8d469f9b2b8)

## Quick Start

```bash
pip install -r requirements.txt
python -m src.crop_calendar        # Opens browser on http://127.0.0.1:8080/
```

1. Click **Load FS25 Defaults** to pre-fill all standard FS25 crops
2. Click any crop name to select it and edit its growth cycles in the sidebar
3. Use the **Sow / Harvest / Dormant / Clear** paint buttons to mark months
4. Click **Export FS25 XML** to write `<fruitType>` XML files
5. Click **Export maps_growth.xml** for a combined scheduling file
6. Click **Export Calendar HTML** for a printable reference

## Project structure

| File | Purpose |
|------|---------|
| `src/utils.py` | `CropConfig`, `GrowthCycle` dataclasses + FS25 default crop presets |
| `src/crop_calendar.py` | Web-based calendar editor (SPA + HTTP server) |
| `src/xml_generator.py` | FS25 XML generation (`<fruitType>`, `<growth>`, `maps_growth.xml`) |
| `tests/test_crop_calendar.py` | 49 unit tests |
| `examples/` | Example project JSON files |
