# FS25 Crop Maker

A web-based toolkit for Farming Simulator 25 modders that covers two main tasks:

1. **Crop Maker** – type a plain-English prompt, auto-detect the crop type, preview placeholder textures, and download a ready-to-use ZIP of all mod files (XML + PNGs).
2. **Crop Calendar** – build a visual growing-season calendar (Planting / Growing / Harvesting) for every FS25 climate zone, then export a reusable JSON config or a standalone HTML reference sheet.

---

## Screenshots

### Crop Maker – prompt → detect → preview → download
![Crop Maker UI](https://github.com/user-attachments/assets/1e0e8cd3-e893-4948-8378-0e5eebc274f1)

### Crop Calendar Editor – interactive month grid
![Crop Calendar UI](https://github.com/user-attachments/assets/7a1290b4-64d0-4d4a-9b42-efdcf7a03d6d)

---

## Requirements

- Python 3.10+
- [Pillow](https://python-pillow.org/) (image generation)
- [Jinja2](https://jinja.palletsprojects.com/) (XML templating)

```bash
pip install -r requirements.txt
```

---

## Quick Start

### Crop Maker (web UI)

```bash
python -m src.crop_maker
# Opens http://127.0.0.1:8081 in your browser automatically
```

1. Type any description in the prompt box (e.g. `"sunflower oilseed crop"`).
2. Click **Detect & Preview** – the tool identifies the crop type and renders the foliage atlas and icon live in the browser.
3. Adjust the identifier, display title, or preset if needed.
4. Click **Generate All Files** – all mod files are written to `./output/<cropName>/`.
5. Click **Download ZIP** to get everything in one archive.

**Headless / CLI mode** (no browser):

```bash
python -m src.crop_maker --name sunflower --title Sunflower --preset oilseed --output ./output
# Or load a saved config:
python -m src.crop_maker --config examples/wheat_config.json --output ./output
```

### Crop Calendar (web UI)

```bash
python -m src.crop_calendar
# Opens http://127.0.0.1:8080 in your browser automatically
```

- Click any month cell to cycle it through **Idle → Plant → Grow → Harvest → Idle**.
- Right-click or double-click a cell to reset it to Idle.
- Use **Save Config (JSON)** to persist your calendar for re-use with the Crop Maker.
- Use **Export Calendar HTML** to generate a standalone, colour-coded reference sheet.
- Use **Load Config…** to reload a previously saved JSON.

---

## Generated Files

For a crop named `sunflower`, the Crop Maker produces:

```
output/sunflower/
├── sunflower.xml                    # FS25 fruitType XML definition
├── sunflower_modDesc_entry.xml      # Snippet to add to your modDesc.xml
├── sunflower_config.json            # Saved config (re-loadable)
└── textures/
    ├── sunflower_DIFFUSE.png        # RGBA foliage atlas  (placeholder – replace with artwork)
    ├── sunflower_NORMAL.png         # Normal-map atlas    (placeholder)
    ├── sunflower_ROUGHNESS.png      # Roughness atlas     (placeholder)
    └── icon_fruitType_sunflower.png # 128×128 minimap icon (placeholder)
```

> **Tip:** The placeholder textures are clearly watermarked. Replace them with your actual artwork before shipping your mod.

---

## Crop Presets

| Preset | Typical crops | Growth states |
|--------|--------------|---------------|
| `grain` | Wheat, Barley, Oat, Rye, Millet | 8 |
| `row_crop` | Corn/Maize, Sorghum, Sugar Cane | 8 |
| `root_crop` | Potato, Sugar Beet, Carrot, Turnip | 6 |
| `oilseed` | Canola, Sunflower, Flax, Hemp | 8 |
| `legume` | Soybean, Pea, Bean, Lentil | 7 |
| `grass` | Grass, Alfalfa, Clover, Ryegrass | 5 |

The Crop Maker ships with a database of **31 real-world crops** with aliases (e.g. "rapeseed" → canola, "maize" → corn).  Unknown crops fall back gracefully to the nearest matching preset.

---

## Climate Zones (Calendar)

| Zone | Typical region |
|------|---------------|
| Temperate | Central/Western Europe, Pacific NW |
| Continental | Eastern Europe, US Midwest |
| Dry | Mediterranean, Great Plains |
| Tropical | Sub-Saharan Africa, South-East Asia |
| Cold | Scandinavia, Canada, Russia |

---

## Project Structure

```
FS25_Crop-maker/
├── src/
│   ├── crop_maker.py        # Web server + CLI for creating crop files
│   ├── crop_calendar.py     # Web server for the calendar editor
│   ├── crop_detector.py     # Keyword-based crop-type detector
│   ├── xml_generator.py     # Jinja2-based XML file generator
│   ├── texture_generator.py # Pillow-based placeholder texture generator
│   └── utils.py             # Shared data structures and constants
├── templates/
│   ├── fruit_type.xml.j2    # FS25 fruitType XML template
│   └── mod_desc_entry.xml.j2
├── examples/
│   ├── wheat_config.json
│   └── corn_config.json
├── tests/                   # unittest test suite (51 tests)
└── requirements.txt
```

---

## Running the Tests

```bash
python -m unittest discover -s tests -v
```

---

## Ports

| Tool | Default port | Flag |
|------|-------------|------|
| Crop Maker | 8081 | `--port` |
| Crop Calendar | 8080 | `--port` |

Both servers bind to `127.0.0.1` only and require no firewall changes.
