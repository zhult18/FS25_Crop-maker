"""FS25 Crop Calendar – web-based UI.

Starts a local HTTP server and opens the crop calendar editor in the default
browser.  No external web framework is required; the server is built on
Python's built-in ``http.server``.

Usage
-----
    # Launch the web UI (opens browser automatically)
    python -m src.crop_calendar

    # Pre-load an existing crop config
    python -m src.crop_calendar --config examples/wheat_config.json

    # Choose a different port or output directory
    python -m src.crop_calendar --port 8181 --output ./my_output

API endpoints (consumed by the browser page)
---------------------------------------------
    GET  /                        → Serve the editor SPA
    GET  /api/presets             → Return available preset names + zones (JSON)
    GET  /api/defaults            → Return FS25 default crop list
    GET  /api/load?path=<file>    → Load a crop config JSON from disk
    POST /api/save                → Persist the current config to disk (JSON)
    POST /api/export-xml          → Generate FS25 XML files and return paths
    POST /api/export-html         → Generate & save a standalone calendar HTML
    POST /api/export-growth-xml   → Generate maps_growth.xml for all crops
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

from .utils import (
    MONTH_ABBR,
    CLIMATE_ZONES,
    CROP_PRESETS,
    FS25_DEFAULT_CROPS,
    GrowthCycle,
    CropConfig,
    ensure_dir,
)
from .xml_generator import (
    build_fruit_type_xml,
    build_maps_growth_xml,
    write_crop_files,
)

# ---------------------------------------------------------------------------
# Standalone calendar HTML export
# ---------------------------------------------------------------------------

_EXPORT_CSS = """
<style>
  body{font-family:Arial,sans-serif;background:#1a1a2e;color:#eee;margin:0;padding:20px}
  h1{color:#e8c84a;text-align:center;margin-bottom:4px}
  p.subtitle{text-align:center;color:#aaa;margin-top:0}
  .cal-wrap{overflow-x:auto;margin-bottom:32px}
  table{border-collapse:collapse;width:100%;min-width:640px}
  th,td{border:1px solid #2d2d3e;padding:6px 4px;text-align:center}
  th{background:#16213e;font-size:.78em;font-weight:700;text-transform:uppercase;
     letter-spacing:.04em;color:#aaa}
  th.crop-head{text-align:left;padding-left:10px;min-width:140px;color:#e8c84a}
  td.crop-label{text-align:left;padding-left:10px;font-weight:600;
     background:#16213e;color:#ccc;font-size:.85em;white-space:nowrap}
  td.cell{min-width:52px;font-size:.75em;font-weight:700}
  .sow{background:#2d6a4f;color:#d4edda}
  .grow{background:#1b4332;color:#a8d5b5}
  .harvest{background:#b8860b;color:#fff8dc}
  .dormant{background:#2a2a3e;color:#666}
  .idle{background:#111;color:#333}
  .legend{display:flex;gap:20px;flex-wrap:wrap;margin:10px 0 20px;
     justify-content:center;font-size:.85em}
  .legend-item{display:flex;align-items:center;gap:6px}
  .swatch{width:16px;height:16px;border-radius:3px}
  .sw-sow{background:#2d6a4f}
  .sw-grow{background:#1b4332}
  .sw-harvest{background:#b8860b}
  .sw-dormant{background:#2a2a3e;border:1px solid #444}
  .sw-idle{background:#111;border:1px solid #333}
  footer{text-align:center;color:#555;font-size:.8em;margin-top:40px}
  h2{color:#e8c84a;font-size:1rem;margin:24px 0 8px;border-bottom:1px solid #2d2d3e;
     padding-bottom:4px}
</style>
"""


def _month_class(month: int, cycle: GrowthCycle) -> str:
    if month in cycle.harvest_months:
        return "harvest"
    if month in cycle.seed_months:
        return "sow"
    if cycle.first_dormant_month and _is_dormant(month, cycle):
        return "dormant"
    grow = cycle.growing_months()
    if month in grow:
        return "grow"
    return "idle"


def _month_label(month: int, cycle: GrowthCycle) -> str:
    if month in cycle.harvest_months:
        return "H"
    if month in cycle.seed_months:
        return "S"
    if cycle.first_dormant_month and _is_dormant(month, cycle):
        return "·"
    if month in cycle.growing_months():
        return "G"
    return "·"


def _is_dormant(month: int, cycle: GrowthCycle) -> bool:
    fd, ld = cycle.first_dormant_month, cycle.last_dormant_month
    if fd == 0:
        return False
    if fd <= ld:
        return fd <= month <= ld
    # wrap-around (e.g. Nov → Feb)
    return month >= fd or month <= ld


def _build_export_row(crop: CropConfig, cycle: GrowthCycle, cycle_idx: int) -> str:
    label = crop.title
    if len(crop.cycles) > 1:
        label += f" (cycle {cycle_idx})"
    cells = "".join(
        '<td class="cell {cls}">{lbl}</td>'.format(
            cls=_month_class(m, cycle),
            lbl=_month_label(m, cycle),
        )
        for m in range(1, 13)
    )
    return f'<tr><td class="crop-label">{label}</td>{cells}</tr>'


def generate_calendar_html(crops: list[CropConfig], output_dir: str | Path) -> Path:
    """Generate a standalone HTML calendar for all *crops* and write to *output_dir*."""
    header_cells = "".join(f"<th>{a}</th>" for a in MONTH_ABBR)
    rows = []
    for crop in crops:
        for i, cycle in enumerate(crop.cycles, start=1):
            rows.append(_build_export_row(crop, cycle, i))

    if not rows:
        table_html = "<p>No crop data defined.</p>"
    else:
        table_html = (
            '<div class="cal-wrap"><table>'
            f'<tr><th class="crop-head">Crop</th>{header_cells}</tr>'
            + "".join(rows)
            + "</table></div>"
        )

    html = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        '<title>FS25 Crop Calendar</title>' + _EXPORT_CSS + "</head><body>"
        "<h1>🌾 FS25 Crop Calendar</h1>"
        '<div class="legend">'
        '<div class="legend-item"><div class="swatch sw-sow"></div> Sow (S)</div>'
        '<div class="legend-item"><div class="swatch sw-grow"></div> Grow (G)</div>'
        '<div class="legend-item"><div class="swatch sw-harvest"></div> Harvest (H)</div>'
        '<div class="legend-item"><div class="swatch sw-dormant"></div> Dormant</div>'
        '<div class="legend-item"><div class="swatch sw-idle"></div> Idle</div>'
        "</div>"
        + table_html
        + "<footer>Generated by FS25 Crop Maker &mdash; "
        "https://github.com/zhult18/FS25_Crop-maker</footer>"
        "</body></html>"
    )
    out = ensure_dir(output_dir)
    dest = out / "crop_calendar.html"
    dest.write_text(html, encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Web-app SPA HTML
# ---------------------------------------------------------------------------

_SPA_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FS25 Crop Calendar Editor</title>
<style>
/* ── Reset & base ───────────────────────────────────────── */
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",Arial,sans-serif;background:#12121f;color:#e0e0e0;min-height:100vh}

/* ── Layout ─────────────────────────────────────────────── */
header{background:#0f3460;padding:14px 24px;display:flex;align-items:center;gap:16px;
       border-bottom:2px solid #e8c84a}
header h1{color:#e8c84a;font-size:1.4rem;flex:1}
header span{color:#aaa;font-size:.82rem}
.app{display:flex;min-height:calc(100vh - 58px)}
aside{width:300px;min-width:240px;background:#16213e;padding:20px;
      border-right:1px solid #1e2a3e;display:flex;flex-direction:column;gap:16px;
      overflow-y:auto}
main{flex:1;padding:24px;overflow-x:auto;min-width:0}

/* ── Sidebar ────────────────────────────────────────────── */
aside h2{font-size:.95rem;color:#e8c84a;border-bottom:1px solid #e8c84a;
         padding-bottom:5px;margin-bottom:4px}
.field{display:flex;flex-direction:column;gap:3px}
.field label{font-size:.73rem;color:#888;text-transform:uppercase;letter-spacing:.06em}
.field input,.field select{background:#0f1a2e;border:1px solid #2a3550;color:#eee;
  padding:7px 10px;border-radius:5px;font-size:.88rem;outline:none;
  transition:border .2s}
.field input:focus,.field select:focus{border-color:#e8c84a}

/* ── Cycle editor ───────────────────────────────────────── */
#cycles-wrap{display:flex;flex-direction:column;gap:12px}
.cycle-card{background:#0f1a2e;border:1px solid #2a3550;border-radius:6px;
            padding:12px;position:relative}
.cycle-card h3{font-size:.82rem;color:#e8c84a;margin-bottom:8px}
.month-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin-bottom:6px}
.month-btn{padding:4px 2px;border:1px solid #2a3550;border-radius:4px;cursor:pointer;
           font-size:.72rem;font-weight:700;text-align:center;transition:all .15s;
           background:#111;color:#555;user-select:none}
.month-btn.sow    {background:#2d6a4f;color:#d4edda;border-color:#2d6a4f}
.month-btn.grow   {background:#1b4332;color:#a8d5b5;border-color:#1b4332}
.month-btn.harvest{background:#b8860b;color:#fff8dc;border-color:#b8860b}
.month-btn.dormant{background:#2a2a3e;color:#666;border-color:#2a2a3e}
.cycle-modes{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px}
.mode-btn{padding:3px 8px;border-radius:4px;border:1px solid #2a3550;cursor:pointer;
          font-size:.72rem;font-weight:600;background:#111;color:#aaa;transition:all .15s}
.mode-btn.active{color:#fff}
.mode-btn[data-mode="sow"].active    {background:#2d6a4f;border-color:#2d6a4f}
.mode-btn[data-mode="harvest"].active{background:#b8860b;border-color:#b8860b}
.mode-btn[data-mode="dormant"].active{background:#2a2a3e;border-color:#555}
.mode-btn[data-mode="clear"].active  {background:#333;border-color:#555}
.dormant-row{display:flex;align-items:center;gap:6px;font-size:.75rem;color:#888;
             margin-top:4px}
.dormant-row select{padding:2px 6px;background:#0f1a2e;border:1px solid #2a3550;
                    color:#ccc;border-radius:4px;font-size:.75rem}
.remove-cycle{position:absolute;top:8px;right:8px;background:transparent;
              border:none;color:#555;font-size:1rem;cursor:pointer;padding:0 4px}
.remove-cycle:hover{color:#e94560}

/* ── Crop list ──────────────────────────────────────────── */
#crop-list{display:flex;flex-direction:column;gap:4px}
.crop-item{display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:5px;
           cursor:pointer;font-size:.82rem;transition:background .15s;border:1px solid transparent}
.crop-item:hover{background:#1e2a3e}
.crop-item.active{background:#1e2a3e;border-color:#e8c84a}
.crop-item-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.crop-item-del{background:transparent;border:none;color:#555;cursor:pointer;
               font-size:.9rem;padding:0 3px;flex-shrink:0}
.crop-item-del:hover{color:#e94560}

/* ── Buttons ────────────────────────────────────────────── */
.btn{display:block;width:100%;padding:8px 14px;border:none;border-radius:6px;
     font-size:.83rem;font-weight:600;cursor:pointer;text-align:center;
     transition:opacity .15s}
.btn:hover{opacity:.85}
.btn-primary  {background:#e8c84a;color:#12121f}
.btn-green    {background:#2d6a4f;color:#fff}
.btn-outline  {background:transparent;border:1px solid #444;color:#bbb}
.btn-danger   {background:#c0392b;color:#fff}
.btn-sm{font-size:.75rem;padding:5px 10px}
.btn-group{display:flex;flex-direction:column;gap:6px}

/* ── Calendar grid (multi-crop overview) ─────────────────── */
.section-title{font-size:1rem;font-weight:700;color:#e8c84a;
  margin-bottom:14px;border-bottom:1px solid #1e2a3e;padding-bottom:6px}
.cal-outer{overflow-x:auto}
table.cal{border-collapse:collapse;min-width:600px;width:100%}
table.cal th,table.cal td{border:1px solid #1e2a3e;padding:0;text-align:center}
table.cal th{background:#16213e;font-size:.72rem;color:#888;padding:6px 2px;
  font-weight:700;text-transform:uppercase;letter-spacing:.04em;min-width:52px}
th.crop-head{text-align:left;padding-left:10px;min-width:150px;
             width:150px;color:#e8c84a;font-size:.8rem}
td.crop-label{text-align:left;padding:6px 8px 6px 10px;font-weight:600;
  color:#ccc;background:#16213e;cursor:pointer;font-size:.8rem;
  white-space:nowrap;max-width:180px;overflow:hidden;text-overflow:ellipsis}
td.crop-label:hover{color:#e8c84a}
td.mc{height:36px;font-size:.72rem;font-weight:700}
td.mc.sow    {background:#2d6a4f;color:#d4edda}
td.mc.grow   {background:#1b4332;color:#a8d5b5}
td.mc.harvest{background:#b8860b;color:#fff8dc}
td.mc.dormant{background:#1c1c2e;color:#444}
td.mc.idle   {background:#111;color:#333}

/* ── Legend ─────────────────────────────────────────────── */
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;align-items:center}
.legend-item{display:flex;align-items:center;gap:5px;font-size:.78rem;color:#aaa}
.sw{width:14px;height:14px;border-radius:3px;flex-shrink:0}
.sw-sow    {background:#2d6a4f}
.sw-grow   {background:#1b4332}
.sw-harvest{background:#b8860b}
.sw-dormant{background:#1c1c2e;border:1px solid #444}
.sw-idle   {background:#111;border:1px solid #333}

/* ── Toast ──────────────────────────────────────────────── */
#toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);
  background:#1e2a3e;color:#eee;padding:10px 22px;border-radius:8px;
  font-size:.85rem;box-shadow:0 4px 16px rgba(0,0,0,.6);
  opacity:0;pointer-events:none;transition:opacity .3s;z-index:999}
#toast.show{opacity:1}
#toast.ok {border-left:4px solid #2d6a4f}
#toast.err{border-left:4px solid #e94560}

/* ── Split pane divider ─────────────────────────────────── */
.split-header{display:flex;align-items:center;justify-content:space-between;
              margin-bottom:10px}

#file-input{display:none}
</style>
</head>
<body>

<header>
  <h1>🌾 FS25 Crop Calendar Editor</h1>
  <span>Build your crop growing season, then export FS25-compatible XML</span>
</header>

<div class="app">

<!-- ═══ Sidebar ════════════════════════════════════════════ -->
<aside>

  <!-- Crop selector -->
  <div>
    <h2>Crops in Project</h2>
    <div id="crop-list"></div>
    <div style="margin-top:8px;display:flex;gap:6px">
      <button class="btn btn-green btn-sm" style="flex:1" onclick="addCrop()">+ New Crop</button>
      <button class="btn btn-outline btn-sm" style="flex:1" onclick="loadFromDefaults()">Load FS25 Defaults</button>
    </div>
  </div>

  <!-- Crop details (shown when a crop is selected) -->
  <div id="crop-detail" style="display:none">
    <h2>Crop Details</h2>
    <div class="field">
      <label>Identifier (XML name)</label>
      <input id="f-name" type="text" placeholder="e.g. myCrop" oninput="onNameChange()">
    </div>
    <div class="field">
      <label>Display Title</label>
      <input id="f-title" type="text" placeholder="e.g. My Crop" oninput="onTitleChange()">
    </div>
    <div class="field">
      <label>Preset</label>
      <select id="f-preset" onchange="onPresetChange()">
        <option value="grain">Grain (wheat, barley, rye…)</option>
        <option value="row_crop">Row Crop (corn/maize…)</option>
        <option value="root_crop">Root Crop (potato, sugarbeet…)</option>
        <option value="oilseed">Oilseed (canola, sunflower…)</option>
        <option value="legume">Legume (soybean, pea…)</option>
        <option value="grass">Grass / Hay</option>
      </select>
    </div>

    <h2>Growth Cycles</h2>
    <p style="font-size:.72rem;color:#666;margin-bottom:8px">
      Each cycle = one sowing window. Add a 2nd cycle for spring+autumn sowing.
    </p>
    <div id="cycles-wrap"></div>
    <button class="btn btn-outline btn-sm" style="margin-top:6px" onclick="addCycle()">+ Add Cycle</button>
  </div>

  <!-- Actions -->
  <div class="btn-group" style="margin-top:auto">
    <button class="btn btn-primary"  onclick="saveConfig()">💾 Save Config (JSON)</button>
    <button class="btn btn-green"    onclick="exportXml()">📄 Export FS25 XML</button>
    <button class="btn btn-outline"  onclick="exportHtml()">🗓 Export Calendar HTML</button>
    <button class="btn btn-outline"  onclick="exportGrowthXml()">🌿 Export maps_growth.xml</button>
    <label  class="btn btn-outline"  for="file-input">📂 Load Config…</label>
    <input  id="file-input" type="file" accept=".json" onchange="loadConfig(event)">
  </div>

</aside>

<!-- ═══ Main calendar ════════════════════════════════════════ -->
<main>
  <div class="split-header">
    <div class="section-title" style="margin-bottom:0">Growing Season Calendar</div>
    <span style="font-size:.75rem;color:#555">Click a crop name to select and edit it</span>
  </div>

  <div class="legend">
    <div class="legend-item"><div class="sw sw-sow"></div>    Sow (S)</div>
    <div class="legend-item"><div class="sw sw-grow"></div>   Grow (G)</div>
    <div class="legend-item"><div class="sw sw-harvest"></div>Harvest (H)</div>
    <div class="legend-item"><div class="sw sw-dormant"></div>Dormant</div>
    <div class="legend-item"><div class="sw sw-idle"></div>   Idle</div>
  </div>

  <div class="cal-outer">
    <table class="cal" id="cal-table"><!-- built by JS --></table>
  </div>

  <p id="cal-empty" style="color:#555;margin-top:40px;text-align:center;display:none">
    No crops yet — add a crop using the sidebar.
  </p>
</main>
</div>

<div id="toast"></div>

<script>
/* ── Constants ─────────────────────────────────────────── */
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const STATES = ["sow","harvest","dormant","clear"];
const STATE_LABELS = {sow:"S", grow:"G", harvest:"H", dormant:"·", idle:"·"};

/* ── Application state ─────────────────────────────────── */
// crops: array of {name, title, preset, cycles:[{seed_months, harvest_months,
//         first_dormant_month, last_dormant_month}]}
let crops = [];
let selectedIdx = -1;   // index into crops[]
let activeMode = "sow"; // current paint mode in cycle editor

/* ════════════════════════════════════════════════════════════
   Derived helpers
   ════════════════════════════════════════════════════════════ */
function growingMonths(cycle) {
  const {seed_months:S, harvest_months:H} = cycle;
  if (!S.length || !H.length) return [];
  const minS = Math.min(...S), maxH = Math.max(...H);
  const res = [];
  if (maxH >= minS) {
    for (let m=1; m<=12; m++)
      if (m > minS && m < maxH && !S.includes(m) && !H.includes(m)) res.push(m);
  } else {
    for (let m=1; m<=12; m++) {
      const after = m > minS || m < maxH;
      if (after && !S.includes(m) && !H.includes(m)) res.push(m);
    }
  }
  return res;
}

function isDormant(month, cycle) {
  const {first_dormant_month:fd, last_dormant_month:ld} = cycle;
  if (!fd) return false;
  if (fd <= ld) return month >= fd && month <= ld;
  return month >= fd || month <= ld;
}

function monthClass(month, cycle) {
  if (cycle.harvest_months.includes(month)) return "harvest";
  if (cycle.seed_months.includes(month))    return "sow";
  if (isDormant(month, cycle))              return "dormant";
  if (growingMonths(cycle).includes(month)) return "grow";
  return "idle";
}

function monthLabel(month, cycle) {
  const cls = monthClass(month, cycle);
  if (cls === "sow")     return "S";
  if (cls === "harvest") return "H";
  if (cls === "grow")    return "G";
  return "·";
}

/* ════════════════════════════════════════════════════════════
   Calendar grid (multi-crop overview)
   ════════════════════════════════════════════════════════════ */
function rebuildCalendar() {
  const tbl = document.getElementById("cal-table");
  const empty = document.getElementById("cal-empty");

  // Gather all rows (one per cycle per crop)
  const rows = [];
  crops.forEach((crop, ci) => {
    (crop.cycles || []).forEach((cycle, ki) => {
      rows.push({crop, ci, cycle, ki});
    });
    if (!crop.cycles || !crop.cycles.length) {
      rows.push({crop, ci, cycle: null, ki: -1});
    }
  });

  if (!rows.length) {
    tbl.innerHTML = "";
    empty.style.display = "";
    return;
  }
  empty.style.display = "none";

  const headerCells = MONTHS.map(m => `<th>${m}</th>`).join("");
  let html = `<tr><th class="crop-head">Crop / Cycle</th>${headerCells}</tr>`;

  rows.forEach(({crop, ci, cycle, ki}) => {
    const isSelected = ci === selectedIdx;
    const label = (crop.cycles && crop.cycles.length > 1)
      ? `${crop.title} <span style="color:#666;font-size:.7em">(cycle ${ki+1})</span>`
      : crop.title;
    let cells = "";
    for (let m = 1; m <= 12; m++) {
      const cls = cycle ? monthClass(m, cycle) : "idle";
      const lbl = cycle ? monthLabel(m, cycle) : "·";
      cells += `<td class="mc ${cls}">${lbl}</td>`;
    }
    const rowStyle = isSelected ? ' style="outline:2px solid #e8c84a;outline-offset:-2px"' : "";
    html += `<tr${rowStyle}>
      <td class="crop-label" onclick="selectCrop(${ci})">${label}</td>${cells}
    </tr>`;
  });

  tbl.innerHTML = html;
}

/* ════════════════════════════════════════════════════════════
   Sidebar – crop list
   ════════════════════════════════════════════════════════════ */
function rebuildCropList() {
  const list = document.getElementById("crop-list");
  if (!crops.length) {
    list.innerHTML = '<p style="font-size:.75rem;color:#555;padding:4px">No crops yet.</p>';
    return;
  }
  list.innerHTML = crops.map((c, i) => `
    <div class="crop-item${i===selectedIdx?' active':''}" onclick="selectCrop(${i})">
      <span class="crop-item-name">${c.title || c.name || "(unnamed)"}</span>
      <button class="crop-item-del" title="Remove" onclick="removeCrop(event,${i})">✕</button>
    </div>
  `).join("");
}

function selectCrop(idx) {
  selectedIdx = idx;
  rebuildCropList();
  rebuildCalendar();
  showCropDetail();
}

function showCropDetail() {
  const detail = document.getElementById("crop-detail");
  if (selectedIdx < 0 || selectedIdx >= crops.length) {
    detail.style.display = "none";
    return;
  }
  detail.style.display = "";
  const crop = crops[selectedIdx];
  document.getElementById("f-name").value  = crop.name  || "";
  document.getElementById("f-title").value = crop.title || "";
  document.getElementById("f-preset").value = crop.preset || "grain";
  rebuildCycleCards();
}

/* ════════════════════════════════════════════════════════════
   Sidebar – crop CRUD
   ════════════════════════════════════════════════════════════ */
function addCrop() {
  const name = `crop${crops.length + 1}`;
  crops.push({
    name, title: `Crop ${crops.length + 1}`, preset: "grain",
    cycles: [{seed_months:[], harvest_months:[], first_dormant_month:0, last_dormant_month:0}]
  });
  selectCrop(crops.length - 1);
}

function removeCrop(evt, idx) {
  evt.stopPropagation();
  crops.splice(idx, 1);
  if (selectedIdx >= crops.length) selectedIdx = crops.length - 1;
  rebuildCropList();
  rebuildCalendar();
  showCropDetail();
}

function onNameChange()   { if (selectedIdx>=0) { crops[selectedIdx].name  = document.getElementById("f-name").value.trim() || "crop"; rebuildCropList(); } }
function onTitleChange()  { if (selectedIdx>=0) { crops[selectedIdx].title = document.getElementById("f-title").value.trim() || "Crop"; rebuildCropList(); rebuildCalendar(); } }
function onPresetChange() { if (selectedIdx>=0) { crops[selectedIdx].preset = document.getElementById("f-preset").value; } }

async function loadFromDefaults() {
  const r = await fetch("/api/defaults");
  const data = await r.json();
  crops = data.crops;
  selectedIdx = crops.length ? 0 : -1;
  rebuildCropList();
  rebuildCalendar();
  showCropDetail();
  toast("✅ Loaded FS25 default crops", "ok");
}

/* ════════════════════════════════════════════════════════════
   Cycle cards
   ════════════════════════════════════════════════════════════ */
function addCycle() {
  if (selectedIdx < 0) return;
  crops[selectedIdx].cycles.push({seed_months:[], harvest_months:[], first_dormant_month:0, last_dormant_month:0});
  rebuildCycleCards();
  rebuildCalendar();
}

function removeCycle(ki) {
  if (selectedIdx < 0) return;
  crops[selectedIdx].cycles.splice(ki, 1);
  rebuildCycleCards();
  rebuildCalendar();
}

function rebuildCycleCards() {
  if (selectedIdx < 0) return;
  const crop = crops[selectedIdx];
  const wrap = document.getElementById("cycles-wrap");
  wrap.innerHTML = "";
  (crop.cycles || []).forEach((cycle, ki) => {
    wrap.appendChild(buildCycleCard(cycle, ki));
  });
}

function buildCycleCard(cycle, ki) {
  const card = document.createElement("div");
  card.className = "cycle-card";
  card.innerHTML = `
    <h3>Cycle ${ki+1}</h3>
    <button class="remove-cycle" title="Remove cycle" onclick="removeCycle(${ki})">✕</button>
    <div class="cycle-modes">
      <button class="mode-btn${activeMode==='sow'?' active':''}" data-mode="sow"
        onclick="setMode('sow',this)">🌱 Sow</button>
      <button class="mode-btn${activeMode==='harvest'?' active':''}" data-mode="harvest"
        onclick="setMode('harvest',this)">🌾 Harvest</button>
      <button class="mode-btn${activeMode==='dormant'?' active':''}" data-mode="dormant"
        onclick="setMode('dormant',this)">❄ Dormant</button>
      <button class="mode-btn${activeMode==='clear'?' active':''}" data-mode="clear"
        onclick="setMode('clear',this)">✕ Clear</button>
    </div>
    <div class="month-grid" id="mgrid-${ki}"></div>
    <div class="dormant-row">
      <span>Dormant:</span>
      <select id="dorm-start-${ki}" onchange="onDormChange(${ki})">
        ${dormOptions(cycle.first_dormant_month)}
      </select>
      <span>→</span>
      <select id="dorm-end-${ki}" onchange="onDormChange(${ki})">
        ${dormOptions(cycle.last_dormant_month)}
      </select>
    </div>
  `;
  const grid = card.querySelector(`#mgrid-${ki}`);
  MONTHS.forEach((mn, mi) => {
    const m = mi + 1;
    const btn = document.createElement("button");
    btn.className = "month-btn " + monthClass(m, cycle);
    btn.textContent = mn;
    btn.dataset.month = m;
    btn.dataset.ki = ki;
    btn.addEventListener("click", () => onMonthClick(ki, m));
    btn.id = `mbtn-${ki}-${m}`;
    grid.appendChild(btn);
  });
  return card;
}

function dormOptions(selected) {
  let o = '<option value="0">(none)</option>';
  for (let m=1; m<=12; m++) {
    o += `<option value="${m}"${m===selected?' selected':''}>${MONTHS[m-1]}</option>`;
  }
  return o;
}

function setMode(mode, btn) {
  activeMode = mode;
  document.querySelectorAll(".mode-btn").forEach(b => {
    b.classList.toggle("active", b === btn || b.dataset.mode === mode);
  });
}

function onMonthClick(ki, m) {
  if (selectedIdx < 0) return;
  const cycle = crops[selectedIdx].cycles[ki];
  if (activeMode === "sow") {
    toggle(cycle.seed_months, m);
    // remove from harvest if present
    cycle.harvest_months = cycle.harvest_months.filter(x => x !== m);
  } else if (activeMode === "harvest") {
    toggle(cycle.harvest_months, m);
    cycle.seed_months = cycle.seed_months.filter(x => x !== m);
  } else if (activeMode === "dormant") {
    // dormant is handled by dropdowns; clicking just highlights
  } else if (activeMode === "clear") {
    cycle.seed_months    = cycle.seed_months.filter(x => x !== m);
    cycle.harvest_months = cycle.harvest_months.filter(x => x !== m);
  }
  updateMonthBtn(ki, m, cycle);
  rebuildCalendar();
}

function toggle(arr, val) {
  const i = arr.indexOf(val);
  if (i >= 0) arr.splice(i, 1);
  else arr.push(val);
  arr.sort((a,b) => a-b);
}

function updateMonthBtn(ki, m, cycle) {
  const btn = document.getElementById(`mbtn-${ki}-${m}`);
  if (!btn) return;
  btn.className = "month-btn " + monthClass(m, cycle);
}

function onDormChange(ki) {
  if (selectedIdx < 0) return;
  const cycle = crops[selectedIdx].cycles[ki];
  cycle.first_dormant_month = parseInt(document.getElementById(`dorm-start-${ki}`).value);
  cycle.last_dormant_month  = parseInt(document.getElementById(`dorm-end-${ki}`).value);
  // redraw all month buttons for this cycle
  for (let m=1; m<=12; m++) updateMonthBtn(ki, m, cycle);
  rebuildCalendar();
}

/* ════════════════════════════════════════════════════════════
   Serialise / Deserialise
   ════════════════════════════════════════════════════════════ */
function buildPayload() {
  return {crops};
}

function applyPayload(data) {
  crops = data.crops || [];
  selectedIdx = crops.length ? 0 : -1;
  rebuildCropList();
  rebuildCalendar();
  showCropDetail();
}

/* ════════════════════════════════════════════════════════════
   API calls
   ════════════════════════════════════════════════════════════ */
async function post(url, body) {
  const r = await fetch(url, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body),
  });
  return r.json();
}

async function saveConfig() {
  const data = await post("/api/save", buildPayload());
  if (data.ok) toast(`✅ Saved → ${data.path}`, "ok");
  else         toast(`❌ ${data.error}`, "err");
}

async function exportXml() {
  const data = await post("/api/export-xml", buildPayload());
  if (data.ok) toast(`✅ XML written → ${data.paths.join(", ")}`, "ok");
  else         toast(`❌ ${data.error}`, "err");
}

async function exportHtml() {
  const data = await post("/api/export-html", buildPayload());
  if (data.ok) {
    toast(`✅ Calendar HTML → ${data.path}`, "ok");
    const blob = new Blob([data.html], {type:"text/html"});
    window.open(URL.createObjectURL(blob), "_blank");
  } else toast(`❌ ${data.error}`, "err");
}

async function exportGrowthXml() {
  const data = await post("/api/export-growth-xml", buildPayload());
  if (data.ok) {
    toast(`✅ maps_growth.xml → ${data.path}`, "ok");
  } else toast(`❌ ${data.error}`, "err");
}

function loadConfig(evt) {
  const file = evt.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const cfg = JSON.parse(e.target.result);
      applyPayload(cfg);
      toast(`📂 Loaded: ${file.name}`, "ok");
    } catch {
      toast("❌ Invalid JSON file", "err");
    }
  };
  reader.readAsText(file);
  evt.target.value = "";
}

/* ════════════════════════════════════════════════════════════
   Toast
   ════════════════════════════════════════════════════════════ */
let _tt;
function toast(msg, type="ok") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(_tt);
  _tt = setTimeout(() => el.className="", 4000);
}

/* ════════════════════════════════════════════════════════════
   Init
   ════════════════════════════════════════════════════════════ */
rebuildCropList();
rebuildCalendar();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the crop-calendar SPA."""

    output_dir: Path = Path("./output")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN401
        pass

    # ── routing ─────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(_SPA_HTML)
        elif parsed.path == "/api/presets":
            self._send_json({"presets": list(CROP_PRESETS.keys()), "zones": CLIMATE_ZONES})
        elif parsed.path == "/api/defaults":
            self._send_json({"crops": _build_default_crops_payload()})
        elif parsed.path == "/api/load":
            qs = parse_qs(parsed.query)
            fp = qs.get("path", [None])[0]
            if not fp:
                self._send_json({"ok": False, "error": "No path provided"}, 400)
                return
            try:
                cfg = CropConfig.from_json(fp)
                self._send_json({"ok": True, "config": cfg.to_dict()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON body"}, 400)
            return

        parsed = urlparse(self.path)
        if parsed.path == "/api/save":
            self._handle_save(data)
        elif parsed.path == "/api/export-xml":
            self._handle_export_xml(data)
        elif parsed.path == "/api/export-html":
            self._handle_export_html(data)
        elif parsed.path == "/api/export-growth-xml":
            self._handle_export_growth_xml(data)
        else:
            self._send_json({"error": "Not found"}, 404)

    # ── handlers ────────────────────────────────────────────────────────
    def _handle_save(self, data: dict[str, Any]) -> None:
        try:
            crops = _crops_from_payload(data)
            out = ensure_dir(self.output_dir)
            dest = out / "calendar_project.json"
            dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._send_json({"ok": True, "path": str(dest.resolve())})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def _handle_export_xml(self, data: dict[str, Any]) -> None:
        try:
            crops = _crops_from_payload(data)
            paths = []
            for crop in crops:
                written = write_crop_files(crop, self.output_dir)
                paths.extend(str(p.resolve()) for p in written.values())
            self._send_json({"ok": True, "paths": paths})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def _handle_export_html(self, data: dict[str, Any]) -> None:
        try:
            crops = _crops_from_payload(data)
            dest = generate_calendar_html(crops, self.output_dir)
            html_content = dest.read_text(encoding="utf-8")
            self._send_json({"ok": True, "path": str(dest.resolve()), "html": html_content})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def _handle_export_growth_xml(self, data: dict[str, Any]) -> None:
        try:
            crops = _crops_from_payload(data)
            xml_str = build_maps_growth_xml(crops)
            out = ensure_dir(self.output_dir)
            dest = out / "maps_growth.xml"
            dest.write_text(xml_str, encoding="utf-8")
            self._send_json({"ok": True, "path": str(dest.resolve())})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)

    # ── response helpers ─────────────────────────────────────────────────
    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crops_from_payload(data: dict[str, Any]) -> list[CropConfig]:
    """Build list of CropConfig from the JSON payload sent by the SPA."""
    raw_crops = data.get("crops", [])
    result = []
    for rc in raw_crops:
        name   = rc.get("name", "crop")
        title  = rc.get("title", name)
        preset = rc.get("preset", "grain")
        crop   = CropConfig(name=name, title=title, preset=preset)
        crop.apply_preset()
        crop.cycles = [
            GrowthCycle(
                seed_months=c.get("seed_months", []),
                harvest_months=c.get("harvest_months", []),
                first_dormant_month=c.get("first_dormant_month", 0),
                last_dormant_month=c.get("last_dormant_month", 0),
            )
            for c in rc.get("cycles", [])
        ]
        result.append(crop)
    return result


def _build_default_crops_payload() -> list[dict[str, Any]]:
    """Return the FS25 default crops as the SPA's wire format."""
    out = []
    for name, info in FS25_DEFAULT_CROPS.items():
        out.append({
            "name": name,
            "title": info["title"],
            "preset": info["preset"],
            "cycles": info["cycles"],
        })
    return out


# ---------------------------------------------------------------------------
# Server factory & entry point
# ---------------------------------------------------------------------------

def make_server(port: int, output_dir: str | Path) -> HTTPServer:
    """Create and return the HTTPServer bound to *port*."""

    class _BoundHandler(_Handler):
        pass

    _BoundHandler.output_dir = ensure_dir(output_dir)
    return HTTPServer(("127.0.0.1", port), _BoundHandler)


def main(argv: Optional[list[str]] = None) -> None:  # noqa: UP007
    import argparse

    parser = argparse.ArgumentParser(
        prog="crop_calendar",
        description="FS25 Crop Calendar – web-based editor",
    )
    parser.add_argument("--port", type=int, default=8080,
                        help="Port for the local web server (default: 8080)")
    parser.add_argument("--output", default="./output",
                        help="Directory where exported files are saved (default: ./output)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the browser automatically")
    args = parser.parse_args(argv)

    server = make_server(args.port, args.output)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"🌾  FS25 Crop Calendar  →  {url}")
    print(f"    Exports saved to    →  {Path(args.output).resolve()}")
    print("    Press Ctrl-C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
