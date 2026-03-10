"""FS25 Crop Maker – web-based UI.

Starts a local HTTP server and opens the crop creator in the default browser.
Users type a natural-language prompt; the tool detects the crop type, renders
a live texture preview, and lets them download a ready-to-use ZIP of all mod
files.

Usage
-----
    # Launch (opens browser automatically)
    python -m src.crop_maker

    # Custom port / output directory
    python -m src.crop_maker --port 8081 --output ./my_output

    # Headless (CLI) mode – non-interactive, no browser
    python -m src.crop_maker --name wheat --title Wheat --preset grain --output ./output

API endpoints (consumed by the browser SPA)
-------------------------------------------
    GET  /                      → Serve the editor SPA
    GET  /api/crops             → List all known crops in the database
    POST /api/detect            → { "prompt": "..." }
                                  → { crop_info, preview_diffuse_b64, preview_icon_b64 }
    POST /api/generate          → { "prompt": "...", "name": "...", "title": "...",
                                     "preset": "..." }
                                  → { files[], session_id }
    GET  /api/download?session=<id>  → ZIP binary stream
"""

from __future__ import annotations

import argparse
import io
import json
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs
import threading
import webbrowser

from .utils import CROP_PRESETS, CropConfig, ensure_dir, sanitize_name
from .xml_generator import generate_fruit_type_xml, generate_mod_desc_entry
from .texture_generator import (
    generate_all_textures,
    generate_diffuse_preview_b64,
    generate_icon_preview_b64,
)
from .crop_detector import detect_crop, list_known_crops
from .crop_calendar import generate_calendar_html

# ---------------------------------------------------------------------------
# Session store  (session_id → output directory)
# ---------------------------------------------------------------------------

_MAX_SESSIONS = 20
_sessions: dict[str, Path] = {}


def _new_session(output_dir: Path, crop_name: str) -> str:
    sid = uuid.uuid4().hex
    _sessions[sid] = output_dir / crop_name
    # Evict oldest sessions if we're over the limit
    while len(_sessions) > _MAX_SESSIONS:
        _sessions.pop(next(iter(_sessions)))
    return sid


# ---------------------------------------------------------------------------
# CLI / library entry-point (non-interactive, used by tests)
# ---------------------------------------------------------------------------

def run(crop: CropConfig, output_dir: str | Path, *, verbose: bool = True) -> dict[str, Path]:
    """Generate all FS25 crop files for *crop* inside *output_dir*.

    Returns a mapping of role → generated file path.
    """
    base = ensure_dir(Path(output_dir) / crop.name)
    tex_dir = ensure_dir(base / "textures")

    generated: dict[str, Path] = {}
    generated["fruit_type_xml"] = generate_fruit_type_xml(crop, base)
    generated["mod_desc_entry"] = generate_mod_desc_entry(crop, base)
    textures = generate_all_textures(crop, tex_dir)
    generated.update(textures)
    if crop.calendar:
        generated["calendar_html"] = generate_calendar_html(crop, base)

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
# SPA HTML
# ---------------------------------------------------------------------------

_SPA_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FS25 Crop Maker</title>
<style>
/* ── Reset ──────────────────────────────────────────────── */
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",Arial,sans-serif;background:#12121f;color:#e0e0e0;min-height:100vh;overflow-x:hidden}

/* ── Header ─────────────────────────────────────────────── */
header{background:linear-gradient(135deg,#0f3460 0%,#16213e 100%);
  padding:18px 28px;display:flex;align-items:center;gap:16px;
  border-bottom:2px solid #e94560;box-shadow:0 2px 20px rgba(0,0,0,.4)}
header h1{color:#e94560;font-size:1.5rem;letter-spacing:.03em;flex:1}
header p{color:#7a8aa0;font-size:.82rem}

/* ── Layout ─────────────────────────────────────────────── */
.page{display:grid;grid-template-columns:1fr 1fr;gap:0;min-height:calc(100vh - 66px)}
@media(max-width:860px){.page{grid-template-columns:1fr}}

/* ── Panels ─────────────────────────────────────────────── */
.panel{padding:28px;display:flex;flex-direction:column;gap:20px}
.panel-left{background:#16213e;border-right:1px solid #1e2d40}
.panel-right{background:#12121f}

/* ── Section headings ────────────────────────────────────── */
.section-title{font-size:.75rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.1em;color:#7a8aa0;border-bottom:1px solid #1e2d40;
  padding-bottom:8px;margin-bottom:4px}

/* ── Prompt area ─────────────────────────────────────────── */
.prompt-wrap{position:relative}
textarea#prompt{width:100%;min-height:110px;resize:vertical;
  background:#0d1b2a;border:2px solid #1e2d40;color:#e0e0e0;
  border-radius:10px;padding:14px 16px;font-size:.95rem;line-height:1.5;
  outline:none;transition:border .2s;font-family:inherit}
textarea#prompt:focus{border-color:#e94560}
textarea#prompt::placeholder{color:#3a4a5a}
.prompt-hint{font-size:.72rem;color:#3a5070;margin-top:6px;font-style:italic}

/* ── Buttons ─────────────────────────────────────────────── */
.btn{padding:10px 22px;border:none;border-radius:8px;font-size:.88rem;
  font-weight:700;cursor:pointer;transition:all .18s;letter-spacing:.02em}
.btn:disabled{opacity:.45;cursor:not-allowed}
.btn-detect{background:#e94560;color:#fff;width:100%}
.btn-detect:hover:not(:disabled){background:#c73350}
.btn-generate{background:#2d6a4f;color:#fff;width:100%}
.btn-generate:hover:not(:disabled){background:#1e4d39}
.btn-download{background:#d4a017;color:#111;width:100%}
.btn-download:hover:not(:disabled){background:#b58a10}
.btn-row{display:flex;gap:10px}
.btn-row .btn{flex:1}

/* ── Confidence badge ────────────────────────────────────── */
.badge{display:inline-block;padding:3px 10px;border-radius:20px;
  font-size:.72rem;font-weight:700;letter-spacing:.05em;vertical-align:middle}
.badge-high{background:#2d6a4f;color:#a8efc0}
.badge-medium{background:#7a5c00;color:#ffd77a}
.badge-low{background:#6a1a2a;color:#ffaaaa}

/* ── Detected crop card ──────────────────────────────────── */
.crop-card{background:#0d1b2a;border:1px solid #1e2d40;border-radius:10px;
  padding:16px;display:none;flex-direction:column;gap:12px}
.crop-card.visible{display:flex}
.crop-card h2{font-size:1.1rem;color:#e94560;display:flex;align-items:center;gap:10px}
.crop-card p.desc{font-size:.82rem;color:#7a8aa0;line-height:1.5}
.props-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 16px}
.prop{font-size:.78rem}
.prop span:first-child{color:#7a8aa0;display:block;font-size:.68rem;text-transform:uppercase}
.prop span:last-child{color:#c0d0e0;font-weight:600}

/* ── Editable fields (inline override) ───────────────────── */
.field-row{display:flex;flex-direction:column;gap:4px}
.field-row label{font-size:.68rem;color:#7a8aa0;text-transform:uppercase;letter-spacing:.06em}
.field-row input,.field-row select{background:#12121f;border:1px solid #1e2d40;
  color:#e0e0e0;padding:7px 10px;border-radius:6px;font-size:.88rem;outline:none;
  transition:border .2s;font-family:inherit}
.field-row input:focus,.field-row select:focus{border-color:#e94560}
.fields-2col{display:grid;grid-template-columns:1fr 1fr;gap:10px}

/* ── Texture preview ─────────────────────────────────────── */
.preview-wrap{display:none;flex-direction:column;gap:16px}
.preview-wrap.visible{display:flex}
.preview-grid{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:start}
.preview-main{border-radius:10px;overflow:hidden;border:2px solid #1e2d40;background:#0d1b2a}
.preview-main img{width:100%;display:block;image-rendering:pixelated}
.preview-icon{border-radius:10px;overflow:hidden;border:2px solid #1e2d40;background:#0d1b2a;width:96px}
.preview-icon img{width:96px;height:96px;display:block;image-rendering:pixelated}
.preview-label{font-size:.7rem;color:#7a8aa0;text-align:center;padding:4px 0}

/* ── File list ───────────────────────────────────────────── */
.file-list{list-style:none;display:flex;flex-direction:column;gap:5px}
.file-list li{font-size:.78rem;color:#6a8a6a;display:flex;align-items:center;gap:8px}
.file-list li::before{content:"📄";font-size:.8rem}
.file-list li.xml::before{content:"📋"}
.file-list li.zip::before{content:"📦"}

/* ── Spinner ─────────────────────────────────────────────── */
.spinner{display:none;width:22px;height:22px;border:3px solid #1e2d40;
  border-top-color:#e94560;border-radius:50%;animation:spin .7s linear infinite;
  flex-shrink:0}
.spinner.show{display:inline-block}
@keyframes spin{to{transform:rotate(360deg)}}
.status-row{display:flex;align-items:center;gap:10px;min-height:28px}
.status-msg{font-size:.82rem;color:#7a8aa0;flex:1}

/* ── Toast ───────────────────────────────────────────────── */
#toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);
  background:#16213e;color:#eee;padding:12px 24px;border-radius:8px;
  font-size:.88rem;box-shadow:0 4px 24px rgba(0,0,0,.5);
  opacity:0;pointer-events:none;transition:opacity .3s;z-index:999;
  border:1px solid #1e2d40}
#toast.show{opacity:1}
#toast.ok{border-left:4px solid #2d6a4f}
#toast.err{border-left:4px solid #e94560}

/* ── Divider ─────────────────────────────────────────────── */
.divider{border:none;border-top:1px solid #1e2d40;margin:4px 0}

/* ── Known crops list ────────────────────────────────────── */
.crops-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.chip{background:#0d1b2a;border:1px solid #1e2d40;color:#7a8aa0;
  border-radius:20px;padding:3px 11px;font-size:.72rem;cursor:pointer;
  transition:all .15s;user-select:none}
.chip:hover{border-color:#e94560;color:#e94560}
.chip.grain{border-color:#6a5c30}
.chip.row_crop{border-color:#2a5a30}
.chip.root_crop{border-color:#3a3a8a}
.chip.oilseed{border-color:#6a5a20}
.chip.legume{border-color:#3a5a3a}
.chip.grass{border-color:#2a6a2a}
</style>
</head>
<body>

<header>
  <div>
    <h1>🌾 FS25 Crop Maker</h1>
    <p>Describe a crop → auto-detect → preview textures → download all mod files</p>
  </div>
</header>

<div class="page">

  <!-- ═══════════ LEFT PANEL – Input ════════════════════════════════ -->
  <div class="panel panel-left">

    <div>
      <div class="section-title">Describe Your Crop</div>
      <div class="prompt-wrap">
        <textarea id="prompt"
          placeholder="e.g. &quot;Create a sunflower oilseed crop&quot;  or  &quot;I want a purple amaranth grain&quot;  or just  &quot;carrot&quot;"
        ></textarea>
        <p class="prompt-hint">Plain English is fine – brand names, Latin names, or crop categories all work.</p>
      </div>
      <div style="margin-top:10px">
        <button class="btn btn-detect" id="btn-detect" onclick="doDetect()">
          🔍 Detect &amp; Preview
        </button>
      </div>
      <div class="status-row" style="margin-top:8px">
        <div class="spinner" id="spin-detect"></div>
        <span class="status-msg" id="msg-detect"></span>
      </div>
    </div>

    <hr class="divider">

    <!-- Known crops quick-select -->
    <div>
      <div class="section-title">Known Crops (click to fill prompt)</div>
      <div class="crops-chips" id="crops-chips">Loading…</div>
    </div>

    <hr class="divider">

    <!-- Detected crop card -->
    <div class="crop-card" id="crop-card">
      <h2 id="card-name">–
        <span class="badge" id="card-badge"></span>
      </h2>
      <p class="desc" id="card-desc"></p>

      <!-- Editable name / title / preset -->
      <div class="fields-2col">
        <div class="field-row">
          <label>Identifier (name)</label>
          <input id="f-name" type="text" placeholder="e.g. my_crop">
        </div>
        <div class="field-row">
          <label>Display Title</label>
          <input id="f-title" type="text" placeholder="e.g. My Crop">
        </div>
      </div>
      <div class="field-row">
        <label>Preset</label>
        <select id="f-preset">
          <option value="grain">Grain (wheat, barley, rye…)</option>
          <option value="row_crop">Row Crop (corn/maize…)</option>
          <option value="root_crop">Root Crop (potato, sugarbeet…)</option>
          <option value="oilseed">Oilseed (canola, sunflower…)</option>
          <option value="legume">Legume (soybean, pea…)</option>
          <option value="grass">Grass / Hay</option>
        </select>
      </div>

      <div class="props-grid" id="card-props"></div>

      <button class="btn btn-generate" id="btn-gen" onclick="doGenerate()">
        ⚙️ Generate All Files
      </button>
      <div class="status-row">
        <div class="spinner" id="spin-gen"></div>
        <span class="status-msg" id="msg-gen"></span>
      </div>
    </div>

  </div><!-- /panel-left -->

  <!-- ═══════════ RIGHT PANEL – Preview ════════════════════════════ -->
  <div class="panel panel-right">

    <div>
      <div class="section-title">Texture Preview</div>
      <!-- placeholder before a crop is detected -->
      <div id="preview-placeholder" style="text-align:center;padding:60px 0;color:#3a4a5a;font-size:.9rem">
        ← Describe a crop and click <strong style="color:#e94560">Detect &amp; Preview</strong>
        <br><br>
        The foliage atlas and icon will appear here.
      </div>
    </div>

    <!-- Actual preview (hidden until populated) -->
    <div class="preview-wrap" id="preview-wrap">
      <div class="preview-grid">
        <div>
          <div class="preview-label">Diffuse Atlas (foliage growth stages)</div>
          <div class="preview-main">
            <img id="img-diffuse" src="" alt="Diffuse atlas preview">
          </div>
        </div>
        <div>
          <div class="preview-label">Icon</div>
          <div class="preview-icon">
            <img id="img-icon" src="" alt="Crop icon preview">
          </div>
        </div>
      </div>

      <hr class="divider">

      <!-- File list + download (shown after generate) -->
      <div id="gen-results" style="display:none">
        <div class="section-title">Generated Files</div>
        <ul class="file-list" id="file-list"></ul>
        <div style="margin-top:14px">
          <button class="btn btn-download" id="btn-dl" onclick="doDownload()">
            ⬇ Download ZIP
          </button>
        </div>
      </div>
    </div>

  </div><!-- /panel-right -->

</div><!-- /page -->

<div id="toast"></div>

<script>
/* ── State ──────────────────────────────────────────────────────────────── */
let _session = null;

/* ── Toast ──────────────────────────────────────────────────────────────── */
let _tt;
function toast(msg, type="ok"){
  const el=document.getElementById("toast");
  el.textContent=msg; el.className=`show ${type}`;
  clearTimeout(_tt); _tt=setTimeout(()=>el.className="",3500);
}

/* ── Spinner helpers ────────────────────────────────────────────────────── */
function spin(id,on){document.getElementById(id).classList.toggle("show",on)}
function msg(id,text){document.getElementById(id).textContent=text}

/* ── Load known crops ───────────────────────────────────────────────────── */
async function loadCrops(){
  try{
    const r=await fetch("/api/crops");
    const data=await r.json();
    const wrap=document.getElementById("crops-chips");
    wrap.innerHTML="";
    data.crops.forEach(c=>{
      const el=document.createElement("span");
      el.className=`chip ${c.preset}`;
      el.title=`${c.title} – ${c.description}`;
      el.textContent=c.title;
      el.onclick=()=>{
        document.getElementById("prompt").value=c.title;
        doDetect();
      };
      wrap.appendChild(el);
    });
  }catch(e){document.getElementById("crops-chips").textContent="(unavailable)";}
}

/* ── Detect ─────────────────────────────────────────────────────────────── */
async function doDetect(){
  const prompt=document.getElementById("prompt").value.trim();
  if(!prompt){toast("Please type a crop description first","err");return;}

  spin("spin-detect",true);
  msg("msg-detect","Analysing prompt…");
  document.getElementById("btn-detect").disabled=true;
  document.getElementById("crop-card").classList.remove("visible");
  document.getElementById("preview-wrap").classList.remove("visible");
  document.getElementById("preview-placeholder").style.display="block";
  document.getElementById("gen-results").style.display="none";
  _session=null;

  try{
    const r=await fetch("/api/detect",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({prompt}),
    });
    const data=await r.json();
    if(!data.ok){toast("❌ "+data.error,"err");return;}
    populateCard(data);
    populatePreview(data);
    msg("msg-detect",`Detected: ${data.crop.title}  (${data.crop.confidence_label} confidence)`);
    toast(`🌾 Detected: ${data.crop.title}`,"ok");
  }catch(e){
    toast("❌ Server error: "+e.message,"err");
    msg("msg-detect","");
  }finally{
    spin("spin-detect",false);
    document.getElementById("btn-detect").disabled=false;
  }
}

function populateCard(data){
  const c=data.crop;
  document.getElementById("card-name").childNodes[0].nodeValue=c.title+" ";
  const badge=document.getElementById("card-badge");
  badge.textContent=c.confidence_label+" confidence";
  badge.className=`badge badge-${c.confidence_label.toLowerCase()}`;
  document.getElementById("card-desc").textContent=c.description;
  document.getElementById("f-name").value=c.crop_name;
  document.getElementById("f-title").value=c.title;
  document.getElementById("f-preset").value=c.preset;

  // Properties grid
  const grid=document.getElementById("card-props");
  grid.innerHTML="";
  const props=[
    ["Preset",c.preset.replace("_"," ")],
    ["Matched keyword",c.matched_keyword],
    ["Growth states",c.num_growth_states],
    ["Harvest state",c.min_harvesting_state],
    ["Atlas size",c.atlas_size+"×"+c.atlas_size],
    ["Texture size",c.texture_size+"px"],
  ];
  props.forEach(([k,v])=>{
    grid.innerHTML+=`<div class="prop"><span>${k}</span><span>${v}</span></div>`;
  });

  document.getElementById("crop-card").classList.add("visible");
}

function populatePreview(data){
  document.getElementById("img-diffuse").src="data:image/png;base64,"+data.preview_diffuse_b64;
  document.getElementById("img-icon").src="data:image/png;base64,"+data.preview_icon_b64;
  document.getElementById("preview-placeholder").style.display="none";
  document.getElementById("preview-wrap").classList.add("visible");
}

/* ── Generate ───────────────────────────────────────────────────────────── */
async function doGenerate(){
  const prompt=document.getElementById("prompt").value.trim();
  const name=document.getElementById("f-name").value.trim()||"my_crop";
  const title=document.getElementById("f-title").value.trim()||name;
  const preset=document.getElementById("f-preset").value;

  spin("spin-gen",true);
  msg("msg-gen","Generating files…");
  document.getElementById("btn-gen").disabled=true;
  document.getElementById("gen-results").style.display="none";

  try{
    const r=await fetch("/api/generate",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({prompt,name,title,preset}),
    });
    const data=await r.json();
    if(!data.ok){toast("❌ "+data.error,"err");return;}
    _session=data.session_id;

    // Update preview with full-res diffuse (regenerated server-side)
    if(data.preview_diffuse_b64){
      document.getElementById("img-diffuse").src="data:image/png;base64,"+data.preview_diffuse_b64;
    }
    if(data.preview_icon_b64){
      document.getElementById("img-icon").src="data:image/png;base64,"+data.preview_icon_b64;
    }

    // File list
    const ul=document.getElementById("file-list");
    ul.innerHTML="";
    data.files.forEach(f=>{
      const li=document.createElement("li");
      const ext=f.split(".").pop();
      if(ext==="xml")li.className="xml";
      li.textContent=f;
      ul.appendChild(li);
    });

    document.getElementById("gen-results").style.display="block";
    msg("msg-gen","All files ready!");
    toast("✅ Files generated – click Download ZIP","ok");
  }catch(e){
    toast("❌ Server error: "+e.message,"err");
    msg("msg-gen","");
  }finally{
    spin("spin-gen",false);
    document.getElementById("btn-gen").disabled=false;
  }
}

/* ── Download ZIP ───────────────────────────────────────────────────────── */
async function doDownload(){
  if(!_session){toast("Generate files first","err");return;}
  const a=document.createElement("a");
  a.href=`/api/download?session=${_session}`;
  a.download="crop_files.zip";
  a.click();
}

/* ── Handle Enter key in textarea ───────────────────────────────────────── */
document.addEventListener("DOMContentLoaded",()=>{
  loadCrops();
  document.getElementById("prompt").addEventListener("keydown",e=>{
    if(e.key==="Enter"&&(e.ctrlKey||e.metaKey)){e.preventDefault();doDetect();}
  });
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    output_dir: Path = Path("./output")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN401
        pass  # suppress default request logs

    # ── routing ────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(_SPA_HTML)
        elif parsed.path == "/api/crops":
            self._send_json({"crops": list_known_crops()})
        elif parsed.path == "/api/download":
            qs = parse_qs(parsed.query)
            sid = qs.get("session", [None])[0]
            self._handle_download(sid)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON"}, 400)
            return

        parsed = urlparse(self.path)
        if parsed.path == "/api/detect":
            self._handle_detect(data)
        elif parsed.path == "/api/generate":
            self._handle_generate(data)
        else:
            self._send_json({"error": "Not found"}, 404)

    # ── handlers ──────────────────────────────────────────────────────────

    def _handle_detect(self, data: dict[str, Any]) -> None:
        prompt = data.get("prompt", "").strip()
        if not prompt:
            self._send_json({"ok": False, "error": "prompt is required"}, 400)
            return
        try:
            match = detect_crop(prompt)
            crop = match.config
            self._send_json({
                "ok": True,
                "crop": {
                    "crop_name": match.crop_name,
                    "title": match.title,
                    "preset": match.preset,
                    "description": match.description,
                    "confidence": match.confidence,
                    "confidence_label": match.confidence_label,
                    "matched_keyword": match.matched_keyword,
                    "num_growth_states": crop.numGrowthStates,
                    "min_harvesting_state": crop.minHarvestingGrowthState,
                    "atlas_size": crop.atlasSize,
                    "texture_size": crop.textureSize,
                },
                "preview_diffuse_b64": generate_diffuse_preview_b64(crop, 512),
                "preview_icon_b64": generate_icon_preview_b64(crop),
            })
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def _handle_generate(self, data: dict[str, Any]) -> None:
        prompt = data.get("prompt", "")
        name   = sanitize_name(data.get("name", "") or "my_crop")
        title  = data.get("title", "") or name.replace("_", " ").capitalize()
        preset = data.get("preset", "grain")
        if preset not in CROP_PRESETS:
            preset = "grain"

        try:
            # Build config – honour the user's edited name/title/preset even if
            # they differ from what the detector chose
            crop = CropConfig(name=name, title=title, preset=preset)
            crop.apply_preset()

            generated = run(crop, self.output_dir, verbose=False)
            sid = _new_session(self.output_dir, crop.name)

            # Relative file names for the UI list
            base = self.output_dir / crop.name
            file_names = [str(p.relative_to(base)) for p in generated.values()]

            self._send_json({
                "ok": True,
                "session_id": sid,
                "files": file_names,
                "preview_diffuse_b64": generate_diffuse_preview_b64(crop, 512),
                "preview_icon_b64": generate_icon_preview_b64(crop),
            })
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def _handle_download(self, session_id: Optional[str]) -> None:
        if not session_id or session_id not in _sessions:
            self._send_json({"error": "Session not found – generate files first"}, 404)
            return

        crop_dir = _sessions[session_id]
        if not crop_dir.is_dir():
            self._send_json({"error": "Output directory missing"}, 500)
            return

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in sorted(crop_dir.rglob("*")):
                if fpath.is_file():
                    zf.write(fpath, fpath.relative_to(crop_dir.parent))
        zip_bytes = buf.getvalue()

        zip_name = f"{crop_dir.name}_mod_files.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{zip_name}"')
        self.send_header("Content-Length", str(len(zip_bytes)))
        self.end_headers()
        self.wfile.write(zip_bytes)

    # ── response helpers ──────────────────────────────────────────────────

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
# Server factory & entry point
# ---------------------------------------------------------------------------

def make_server(port: int, output_dir: str | Path) -> HTTPServer:
    class _BoundHandler(_Handler):
        pass
    _BoundHandler.output_dir = ensure_dir(output_dir)
    return HTTPServer(("127.0.0.1", port), _BoundHandler)


def main(argv: Optional[list[str]] = None) -> None:  # noqa: UP007
    parser = argparse.ArgumentParser(
        prog="crop_maker",
        description="FS25 Crop Maker – web-based crop creator with texture preview",
    )
    # Web-server flags
    parser.add_argument("--port", type=int, default=8081,
                        help="Port for the local web server (default: 8081)")
    parser.add_argument("--output", default="./output",
                        help="Directory where files are saved (default: ./output)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the browser automatically")
    # Headless / CLI flags (bypass the web server)
    parser.add_argument("--name",   help="(Headless) crop identifier")
    parser.add_argument("--title",  help="(Headless) crop display title")
    parser.add_argument("--preset", choices=list(CROP_PRESETS.keys()),
                        default="grain", help="(Headless) crop preset")
    parser.add_argument("--config", help="(Headless) path to an existing crop JSON config")
    args = parser.parse_args(argv)

    # ── Headless / CLI mode ────────────────────────────────────────────────
    if args.config or args.name:
        if args.config:
            crop = CropConfig.from_json(args.config)
        else:
            name = sanitize_name(args.name)
            title = args.title or name.replace("_", " ").capitalize()
            crop = CropConfig(name=name, title=title, preset=args.preset)
            crop.apply_preset()
        run(crop, args.output)
        return

    # ── Web server mode ────────────────────────────────────────────────────
    server = make_server(args.port, args.output)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"🌾  FS25 Crop Maker  →  {url}")
    print(f"    Exports saved to →  {Path(args.output).resolve()}")
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
