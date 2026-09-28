// Procedural side-view crop foliage textures for FS25 crop mods.
//
// A crop's look is a "design": plant structure (form, height, stems), leaf shape, head/fruit type and
// colors for each part at green and ripe. generatePlantTexture draws one growth stage of a design as a
// horizontally tiling billboard texture; encodeDds and generateNormalMap turn it into game files.
(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // Small helpers
  // ---------------------------------------------------------------------------

  function clamp01(v) {
    return Math.max(0, Math.min(1, v));
  }

  function makeSeedRng(seed) {
    let s = seed >>> 0;
    return function () {
      s = (s + 0x6d2b79f5) >>> 0;
      let t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashString(text) {
    let h = 0x12345678;
    for (let i = 0; i < text.length; i++) {
      h = ((h * 31) + text.charCodeAt(i)) >>> 0;
    }
    return h;
  }

  function hexToRgb(hex) {
    const h = String(hex || "#000000").replace("#", "");
    return { r: parseInt(h.slice(0, 2), 16) || 0, g: parseInt(h.slice(2, 4), 16) || 0, b: parseInt(h.slice(4, 6), 16) || 0 };
  }

  function lerpHex(c1, c2, t) {
    t = clamp01(t);
    const a = hexToRgb(c1);
    const b = hexToRgb(c2);
    const ch = (x, y) => Math.round(x + (y - x) * t).toString(16).padStart(2, "0");
    return "#" + ch(a.r, b.r) + ch(a.g, b.g) + ch(a.b, b.b);
  }

  function shadeHex(hex, amount) {
    return amount >= 0 ? lerpHex(hex, "#ffffff", amount) : lerpHex(hex, "#000000", -amount);
  }

  // Direction angle convention: 0 points straight up, positive turns clockwise (to the right).
  function dirPoint(p, angle, len) {
    return { x: p.x + Math.sin(angle) * len, y: p.y - Math.cos(angle) * len };
  }

  function quadPoint(p0, p1, p2, t) {
    const mt = 1 - t;
    return {
      x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
      y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y
    };
  }

  function quadAngle(p0, p1, p2, t) {
    const mt = 1 - t;
    const dx = 2 * mt * (p1.x - p0.x) + 2 * t * (p2.x - p1.x);
    const dy = 2 * mt * (p1.y - p0.y) + 2 * t * (p2.y - p1.y);
    return Math.atan2(dx, -dy);
  }

  // A curve leaving p in direction angle that bends toward the ground by droop (0..1).
  function droopCurve(p, angle, len, droop) {
    const mid = dirPoint(p, angle, len * 0.5);
    const side = Math.sin(angle) >= 0 ? 1 : -1;
    const endAngle = angle + side * droop * 1.7;
    return [p, mid, dirPoint(mid, endAngle, len * 0.55)];
  }

  function drawRibbon(ctx, p0, p1, p2, widthAt, fill) {
    const steps = 18;
    const left = [];
    const right = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const { x, y } = quadPoint(p0, p1, p2, t);
      const a = quadAngle(p0, p1, p2, t);
      const nx = Math.cos(a);
      const ny = Math.sin(a);
      const hw = widthAt(t) / 2;
      left.push([x - nx * hw, y - ny * hw]);
      right.push([x + nx * hw, y + ny * hw]);
    }
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.moveTo(left[0][0], left[0][1]);
    left.forEach(([x, y]) => ctx.lineTo(x, y));
    for (let i = right.length - 1; i >= 0; i--) {
      ctx.lineTo(right[i][0], right[i][1]);
    }
    ctx.closePath();
    ctx.fill();
  }

  function strokeQuad(ctx, p0, p1, p2, color, width, fromT = 0, toT = 1) {
    const a = quadPoint(p0, p1, p2, fromT);
    const m = quadPoint(p0, p1, p2, (fromT + toT) / 2);
    const b = quadPoint(p0, p1, p2, toT);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.quadraticCurveTo(2 * m.x - (a.x + b.x) / 2, 2 * m.y - (a.y + b.y) / 2, b.x, b.y);
    ctx.stroke();
  }

  function withAlpha(ctx, alpha, fn) {
    const prev = ctx.globalAlpha;
    ctx.globalAlpha = prev * alpha;
    fn();
    ctx.globalAlpha = prev;
  }

  function inLocalFrame(ctx, p, angle, fn, scaleX = 1) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(angle);
    ctx.scale(scaleX, 1);
    fn();
    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // Designs and presets
  // ---------------------------------------------------------------------------

  // Every field a design can hold. Sizes are fractions of the texture height unless noted.
  const DEFAULT_DESIGN = {
    form: "stalk",          // stalk | bush | rosette | vine
    height: 0.72,           // mature height of the tallest stems
    stems: 3,               // stems (tillers / branches) per plant
    spread: 0.12,           // how far stems fan out from vertical (radians)
    stemWidth: 0.0045,
    stemNodes: true,        // visible joints (grasses, cane)
    stemShow: 0.45,         // growth fraction at which the stem shows above the leaves
    density: 28,            // plants across a square texture
    leafShape: "strap",     // strap | tubular | broad | heart | trifoliate | pinnate | feathery | palmate | lobed
    leafLength: 0.2,
    leafWidth: 0.045,       // width relative to leaf length
    leafCount: 5,           // leaves per stem at maturity
    leafFrom: 0,            // lowest leaf position along the stem (0 = ground, 1 = top)
    leafTo: 0.8,            // highest leaf position along the stem
    leafDroop: 0.35,
    leaflets: 3,            // pairs of leaflets for pinnate leaves
    leafDrop: 0.3,          // share of leaves lost by full ripeness
    head: "spike",          // none | spike | panicle | tassel | disc | raceme | pods | bolls | flowers
    headLen: 0.085,
    headW: 0.022,
    spikelets: 10,          // kernels per spike, spikelets per panicle
    rows: 2,                // kernel rows visible on a spike (3 gives a six-row look)
    awn: 0,
    awnSpread: 0.1,
    nod: 0.4,               // how far heads/pods hang when ripe (radians)
    headCount: 6,           // pods, bolls or flowers per stem
    headStart: 0.55,        // growth fraction when heads appear
    flowerStart: 0.5,
    flowerEnd: 0.72,
    ripenStart: 0.7,
    stemGreen: "#5f8434",
    leafGreen: "#6f9a3e",
    headGreen: "#86a652",
    flowerColor: "#f2e04a",
    veinColor: "",
    stemRipe: "#c2a868",
    leafRipe: "#b39660",
    headRipe: "#c9a24a",
    awnRipe: "#d8b664"
  };

  const GRAIN = { form: "stalk", leafShape: "strap", stemNodes: true, stemShow: 0.45, stems: 3, spread: 0.12, density: 28 };
  const WIDE_STRAP = { form: "stalk", leafShape: "strap", stemNodes: true, stemShow: 0.3, stems: 1, spread: 0.12, density: 11, leafDroop: 0.55 };

  // group: "FS25" for base-game crops, "US" for US crops not in the base game, "Generic" for starting shapes.
  const PLANT_PRESETS = {
    // --- Generic starting shapes
    CUSTOM: { label: "Plain ear (custom)", group: "Generic", ...GRAIN, head: "spike", ripenStart: 0.68 },
    LEAFY: { label: "Leafy, no head", group: "Generic", ...GRAIN, head: "none" },
    BUSHY: { label: "Bushy broadleaf", group: "Generic", form: "bush", stems: 5, spread: 0.5, density: 10, height: 0.6, stemWidth: 0.006, stemNodes: false, stemShow: 0, leafShape: "broad", leafLength: 0.1, leafWidth: 0.6, leafCount: 8, leafDroop: 0.3, leafDrop: 0, head: "none", ripenStart: 1 },

    // --- FS25 base-game crops
    BARLEY: { label: "Barley", group: "FS25", ...GRAIN, headLen: 0.08, headW: 0.02, spikelets: 11, rows: 3, awn: 2.0, awnSpread: 0.06, nod: 2.4, headRipe: "#d8c28a", awnRipe: "#eee0b4" },
    WHEAT: { label: "Wheat", group: "FS25", ...GRAIN, headLen: 0.085, headW: 0.026, spikelets: 10, awn: 0.2, awnSpread: 0.3, nod: 0.3, headRipe: "#c69c48", awnRipe: "#d6b060" },
    OAT: { label: "Oat", group: "FS25", ...GRAIN, head: "panicle", headLen: 0.14, headW: 0.06, spikelets: 14, nod: 0.5, headRipe: "#dcd2a2", awnRipe: "#e8dfb6" },
    RICE: { label: "Rice", group: "FS25", ...GRAIN, head: "panicle", height: 0.6, stems: 4, headLen: 0.13, headW: 0.03, spikelets: 22, nod: 1.3, headRipe: "#d2b25c", leafRipe: "#a89a58" },
    RICELONGGRAIN: { label: "Long Grain Rice", group: "FS25", ...GRAIN, head: "panicle", height: 0.65, stems: 4, headLen: 0.14, headW: 0.028, spikelets: 24, nod: 1.4, headRipe: "#d6bb6c", leafRipe: "#a89a58" },
    SORGHUM: { label: "Sorghum", group: "FS25", ...WIDE_STRAP, head: "panicle", height: 0.7, stemWidth: 0.01, leafLength: 0.3, leafWidth: 0.09, leafCount: 7, headLen: 0.1, headW: 0.035, spikelets: 26, nod: 0.2, headRipe: "#9b4a2a", stemRipe: "#b8a060", leafRipe: "#9c9058" },
    MAIZE: { label: "Maize", group: "FS25", ...WIDE_STRAP, head: "tassel", height: 0.9, stemWidth: 0.012, leafLength: 0.34, leafWidth: 0.09, leafCount: 9, headLen: 0.11, headW: 0.03, nod: 1.6, headStart: 0.6, flowerColor: "#b5673a", headGreen: "#8fb05a", headRipe: "#c8b27a", awnRipe: "#b89c64", stemRipe: "#bda56c", leafRipe: "#bba36e", leafDrop: 0.1 },
    SUGARCANE: { label: "Sugarcane", group: "FS25", ...WIDE_STRAP, head: "none", height: 0.94, stems: 3, spread: 0.15, density: 10, stemWidth: 0.018, stemShow: 0.2, leafLength: 0.36, leafWidth: 0.06, leafCount: 9, leafFrom: 0.55, leafTo: 1, leafDroop: 0.6, stemGreen: "#7a9a3c", stemRipe: "#8c7a3a", leafRipe: "#8aa050", leafDrop: 0 },
    SUNFLOWER: { label: "Sunflower", group: "FS25", form: "stalk", stems: 1, spread: 0.1, density: 9, height: 0.85, stemWidth: 0.012, stemNodes: false, stemShow: 0, leafShape: "heart", leafLength: 0.2, leafTo: 0.9, leafWidth: 0.85, leafCount: 7, leafDroop: 0.45, leafDrop: 0.3, head: "disc", headW: 0.1, nod: 1.8, headStart: 0.45, flowerStart: 0.5, flowerEnd: 0.72, flowerColor: "#f3c219", headGreen: "#6a8c3a", headRipe: "#5a4630", stemRipe: "#6e5a3a", leafRipe: "#4e4030" },
    CANOLA: { label: "Canola", group: "FS25", form: "stalk", stems: 3, spread: 0.25, density: 20, height: 0.7, stemWidth: 0.005, stemNodes: false, stemShow: 0.35, leafShape: "lobed", leafLength: 0.12, leafWidth: 0.55, leafCount: 5, leafDroop: 0.3, leafDrop: 0.8, head: "raceme", headLen: 0.12, headCount: 10, headStart: 0.45, flowerStart: 0.45, flowerEnd: 0.68, flowerColor: "#f6e21c", leafGreen: "#5f8f5a", stemGreen: "#6a9658", headGreen: "#7fa35a", headRipe: "#8a7048", stemRipe: "#9c8458" },
    SOYBEAN: { label: "Soybean", group: "FS25", form: "bush", stems: 4, spread: 0.55, density: 12, height: 0.5, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.1, leafWidth: 0.55, leafCount: 5, leafDroop: 0.3, leafDrop: 0.95, head: "pods", headLen: 0.03, headW: 0.009, headCount: 7, nod: 0.3, flowerStart: 0.45, flowerEnd: 0.6, flowerColor: "#b89ad8", headGreen: "#7fa04a", headRipe: "#8a6a40", stemRipe: "#7a6040", leafRipe: "#c9a840", ripenStart: 0.72 },
    GREENBEAN: { label: "Green Bean", group: "FS25", form: "bush", stems: 4, spread: 0.55, density: 12, height: 0.42, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.12, leafWidth: 0.7, leafCount: 5, leafDroop: 0.35, leafDrop: 0.1, head: "pods", headLen: 0.06, headW: 0.008, headCount: 6, nod: 2.6, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f4f1e4", headGreen: "#6e9a3e", headRipe: "#7ea846", stemRipe: "#6e8a3c", leafRipe: "#7c9a44", ripenStart: 0.85 },
    PEA: { label: "Pea", group: "FS25", form: "vine", stems: 5, spread: 0.9, density: 12, height: 0.35, stemWidth: 0.003, stemNodes: false, stemShow: 0, leafShape: "pinnate", leaflets: 2, leafLength: 0.1, leafWidth: 0.6, leafCount: 6, leafDroop: 0.2, leafDrop: 0.3, head: "pods", headLen: 0.05, headW: 0.014, headCount: 5, nod: 2.2, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f5f3ee", leafGreen: "#6f9a6a", stemGreen: "#78a070", headGreen: "#78a650", headRipe: "#c2b070", stemRipe: "#b8a070", leafRipe: "#b8a26a" },
    COTTON: { label: "Cotton", group: "FS25", form: "bush", stems: 4, spread: 0.45, density: 10, height: 0.6, stemWidth: 0.006, stemNodes: false, stemShow: 0, leafShape: "lobed", leafLength: 0.12, leafWidth: 0.9, leafCount: 5, leafDroop: 0.25, leafDrop: 0.85, head: "bolls", headW: 0.035, headCount: 5, flowerStart: 0.45, flowerEnd: 0.6, flowerColor: "#f3e7b8", headGreen: "#6e9440", headRipe: "#f7f5ef", stemRipe: "#6a4a30", leafRipe: "#7a4a2a", ripenStart: 0.7 },
    POTATO: { label: "Potato", group: "FS25", form: "bush", stems: 4, spread: 0.6, density: 10, height: 0.45, stemWidth: 0.006, stemNodes: false, stemShow: 0, leafShape: "pinnate", leaflets: 3, leafLength: 0.15, leafWidth: 0.55, leafCount: 5, leafDroop: 0.35, leafDrop: 0.4, head: "flowers", headW: 0.012, headCount: 6, flowerStart: 0.5, flowerEnd: 0.68, flowerColor: "#f1eef6", leafGreen: "#557f34", headGreen: "#557f34", headRipe: "#6a5a3a", stemRipe: "#7a6a44", leafRipe: "#7a6a40", ripenStart: 0.8 },
    SUGARBEET: { label: "Sugar Beet", group: "FS25", form: "rosette", density: 9, height: 0.4, leafShape: "broad", leafLength: 0.3, leafWidth: 0.55, leafCount: 12, leafDroop: 0.35, leafDrop: 0, head: "none", leafGreen: "#4f7f34", veinColor: "#e4ecd0", leafRipe: "#6f8a3c" , ripenStart: 1},
    BEETROOT: { label: "Beet Root", group: "FS25", form: "rosette", density: 11, height: 0.32, leafShape: "broad", leafLength: 0.24, leafWidth: 0.5, leafCount: 10, leafDroop: 0.35, leafDrop: 0, head: "none", leafGreen: "#3f6a2e", veinColor: "#9a2440", leafRipe: "#5a6a32" , ripenStart: 1},
    SPINACH: { label: "Spinach", group: "FS25", form: "rosette", density: 14, height: 0.22, leafShape: "broad", leafLength: 0.17, leafWidth: 0.6, leafCount: 12, leafDroop: 0.45, leafDrop: 0, head: "none", leafGreen: "#2f5e2a", veinColor: "#9cc07a", leafRipe: "#3a6a2e" , ripenStart: 1},
    CARROT: { label: "Carrot", group: "FS25", form: "rosette", density: 16, height: 0.3, leafShape: "feathery", leafLength: 0.26, leafWidth: 0.4, leafCount: 9, leafDroop: 0.3, leafDrop: 0, head: "none", leafGreen: "#4f8a34", leafRipe: "#5f8a3c" , ripenStart: 1},
    PARSNIP: { label: "Parsnip", group: "FS25", form: "rosette", density: 14, height: 0.34, leafShape: "pinnate", leaflets: 3, leafLength: 0.28, leafWidth: 0.5, leafCount: 8, leafDroop: 0.35, leafDrop: 0, head: "none", leafGreen: "#5a8a3a", leafRipe: "#6a8a44" , ripenStart: 1},
    GRASS: { label: "Grass", group: "FS25", ...GRAIN, head: "none", height: 0.5, stems: 5, spread: 0.45, density: 22, stemShow: 2, leafLength: 0.3, leafCount: 3, leafDroop: 0.45, leafDrop: 0, leafGreen: "#5f9a3a", stemGreen: "#5a8f36", leafRipe: "#6f9a44", ripenStart: 1 },
    OILSEEDRADISH: { label: "Oilseed Radish", group: "FS25", form: "rosette", density: 12, height: 0.35, leafShape: "lobed", leafLength: 0.22, leafWidth: 0.5, leafCount: 9, leafDroop: 0.35, leafDrop: 0, head: "none", leafGreen: "#4f8a3a", leafRipe: "#5f8a3c" , ripenStart: 1},

    // --- US crops not in the base game (from USDA NASS acreage data; see docs/US_CROPS.md)
    // Wheat classes and other small grains
    HRWWHEAT: { label: "Hard Red Winter Wheat", group: "US", ...GRAIN, height: 0.68, headLen: 0.085, headW: 0.026, spikelets: 10, awn: 1.1, awnSpread: 0.08, nod: 0.35, leafGreen: "#62905a", stemGreen: "#5c8a50", headRipe: "#b98a4a", awnRipe: "#c9a064" },
    SRWWHEAT: { label: "Soft Red Winter Wheat", group: "US", ...GRAIN, height: 0.74, headLen: 0.09, headW: 0.026, spikelets: 11, awn: 0, nod: 0.3, headRipe: "#b07a44" },
    WHITEWHEAT: { label: "Soft White Wheat", group: "US", ...GRAIN, height: 0.74, headLen: 0.09, headW: 0.025, spikelets: 11, awn: 0.15, awnSpread: 0.3, nod: 0.3, headRipe: "#dcc890", stemRipe: "#d6c28a", leafRipe: "#c8b27a" },
    HRSWHEAT: { label: "Hard Red Spring Wheat", group: "US", ...GRAIN, height: 0.64, headLen: 0.08, headW: 0.026, spikelets: 10, awn: 0.8, awnSpread: 0.1, nod: 0.3, headRipe: "#c0924a", awnRipe: "#cfa464" },
    DURUM: { label: "Durum Wheat", group: "US", ...GRAIN, height: 0.78, headLen: 0.08, headW: 0.03, spikelets: 10, awn: 1.6, awnSpread: 0.05, nod: 0.35, leafGreen: "#5f8f6a", stemGreen: "#5c8a62", headGreen: "#7fa27a", headRipe: "#d9b25a", awnRipe: "#3a2e24" },
    SPELT: { label: "Spelt", group: "US", ...GRAIN, height: 0.84, headLen: 0.11, headW: 0.022, spikelets: 12, awn: 0.2, awnSpread: 0.2, nod: 1.0, headRipe: "#b98a58" },
    RYE: { label: "Rye", group: "US", ...GRAIN, height: 0.9, headLen: 0.11, headW: 0.016, spikelets: 15, awn: 0.9, awnSpread: 0.1, nod: 0.9, leafGreen: "#5f8f6a", stemGreen: "#5c8a62", headRipe: "#b3a07a", awnRipe: "#c8b890" },
    TRITICALE: { label: "Triticale", group: "US", ...GRAIN, height: 0.82, headLen: 0.1, headW: 0.026, spikelets: 12, awn: 1.3, awnSpread: 0.08, nod: 0.5, leafGreen: "#5f8f6a", headRipe: "#c9a660", awnRipe: "#d8bd80" },
    REDOAT: { label: "Red Oat", group: "US", ...GRAIN, head: "panicle", headLen: 0.14, headW: 0.06, spikelets: 14, nod: 0.5, headRipe: "#a8643a", awnRipe: "#b8764a" },
    PROSOMILLET: { label: "Proso Millet", group: "US", ...GRAIN, head: "panicle", height: 0.6, leafWidth: 0.07, headLen: 0.13, headW: 0.035, spikelets: 28, nod: 1.6, headRipe: "#d6a860" },
    PEARLMILLET: { label: "Pearl Millet", group: "US", ...WIDE_STRAP, density: 18, stems: 2, head: "spike", height: 0.88, stemWidth: 0.008, leafLength: 0.28, leafWidth: 0.07, leafCount: 7, headLen: 0.12, headW: 0.03, spikelets: 18, rows: 3, awn: 0, nod: 0.15, headRipe: "#a8a08a", stemRipe: "#b8a870", leafRipe: "#a89a60" },
    WILDRICE: { label: "Wild Rice", group: "US", ...GRAIN, head: "panicle", height: 0.92, stems: 2, leafLength: 0.3, headLen: 0.16, headW: 0.03, spikelets: 18, nod: 0.6, flowerColor: "#b890b0", headRipe: "#4a3a2a", leafRipe: "#b8a860" },
    TEFF: { label: "Teff", group: "US", ...GRAIN, head: "panicle", height: 0.55, stems: 5, spread: 0.3, leafWidth: 0.03, headLen: 0.14, headW: 0.05, spikelets: 30, nod: 1.2, headRipe: "#c8a878" },
    TIMOTHY: { label: "Timothy Hay", group: "US", ...GRAIN, head: "spike", height: 0.62, stems: 4, spread: 0.25, headLen: 0.08, headW: 0.012, spikelets: 16, rows: 3, awn: 0, nod: 0.1, headStart: 0.7, headGreen: "#8aa060", leafDrop: 0, ripenStart: 1 },

    // Corn, sorghum and other tall stalks
    SWEETCORN: { label: "Sweet Corn", group: "US", ...WIDE_STRAP, head: "tassel", height: 0.8, stemWidth: 0.011, leafLength: 0.32, leafWidth: 0.09, leafCount: 8, headLen: 0.1, headW: 0.03, nod: 0.3, headStart: 0.6, flowerColor: "#d8c070", headGreen: "#7fa04a", headRipe: "#7fa04a", awnRipe: "#c8b070", leafDrop: 0, ripenStart: 1 },
    POPCORN: { label: "Popcorn", group: "US", ...WIDE_STRAP, head: "tassel", height: 0.84, stemWidth: 0.01, leafLength: 0.3, leafWidth: 0.08, leafCount: 8, headLen: 0.08, headW: 0.022, nod: 1.4, headStart: 0.6, flowerColor: "#b5673a", headRipe: "#cdb884", awnRipe: "#b89c64", stemRipe: "#bda56c", leafRipe: "#bba36e", leafDrop: 0.1 },
    SORGHUMSUDAN: { label: "Sorghum-Sudangrass", group: "US", ...WIDE_STRAP, head: "panicle", height: 0.9, stems: 3, spread: 0.2, density: 16, stemWidth: 0.007, leafLength: 0.3, leafWidth: 0.07, leafCount: 7, headLen: 0.1, headW: 0.04, spikelets: 18, nod: 0.3, headStart: 0.85, leafDrop: 0, ripenStart: 1 },
    BROOMCORN: { label: "Broomcorn", group: "US", ...WIDE_STRAP, head: "panicle", height: 0.94, stemWidth: 0.01, leafLength: 0.3, leafWidth: 0.08, leafCount: 7, headLen: 0.16, headW: 0.05, spikelets: 22, nod: 1.3, headRipe: "#9a5a30", stemRipe: "#b8a060", leafRipe: "#9c9058" },
    HEMP: { label: "Industrial Hemp", group: "US", form: "stalk", stems: 1, spread: 0.08, density: 22, height: 0.92, stemWidth: 0.008, stemNodes: false, stemShow: 0, leafShape: "palmate", leafLength: 0.22, leafWidth: 0.16, leafCount: 12, leafFrom: 0.1, leafTo: 0.95, leafDroop: 0.3, leafDrop: 0.4, head: "flowers", headW: 0.01, headCount: 8, flowerStart: 0.55, flowerEnd: 0.8, flowerColor: "#b8c890", leafGreen: "#4e7f34", headGreen: "#6a8a44", headRipe: "#7a6040", stemRipe: "#a89060", leafRipe: "#b0a050" },
    SWITCHGRASS: { label: "Switchgrass", group: "US", ...GRAIN, head: "panicle", height: 0.9, stems: 6, spread: 0.3, leafLength: 0.26, headLen: 0.16, headW: 0.06, spikelets: 22, nod: 0.3, headRipe: "#b8a080", leafRipe: "#c0a878", stemRipe: "#c8b088" },

    // Flowers and oilseeds
    CONFECTIONSUNFLOWER: { label: "Confection Sunflower", group: "US", form: "stalk", stems: 1, spread: 0.1, density: 8, height: 0.92, stemWidth: 0.014, stemNodes: false, stemShow: 0, leafShape: "heart", leafLength: 0.22, leafWidth: 0.85, leafCount: 7, leafTo: 0.9, leafDroop: 0.45, leafDrop: 0.3, head: "disc", headW: 0.13, nod: 2.0, headStart: 0.45, flowerStart: 0.5, flowerEnd: 0.72, flowerColor: "#f3c219", headGreen: "#6a8c3a", headRipe: "#5a4630", stemRipe: "#6e5a3a", leafRipe: "#4e4030" },
    SAFFLOWER: { label: "Safflower", group: "US", form: "stalk", stems: 3, spread: 0.35, density: 16, height: 0.62, stemWidth: 0.005, stemNodes: false, stemShow: 0.2, leafShape: "broad", leafLength: 0.08, leafWidth: 0.35, leafCount: 7, leafTo: 0.95, leafDroop: 0.15, leafDrop: 0.3, head: "flowers", headW: 0.016, headCount: 3, flowerStart: 0.5, flowerEnd: 0.72, flowerColor: "#f08a1a", leafGreen: "#6f8f6a", headGreen: "#6f8f6a", headRipe: "#b8a070", stemRipe: "#c0a878", leafRipe: "#b8a070" },
    FLAX: { label: "Flax", group: "US", form: "stalk", stems: 3, spread: 0.2, density: 30, height: 0.58, stemWidth: 0.003, stemNodes: false, stemShow: 0.2, leafShape: "strap", leafLength: 0.05, leafWidth: 0.12, leafCount: 10, leafTo: 0.9, leafDroop: 0.1, leafDrop: 0.6, head: "flowers", headW: 0.009, headCount: 5, flowerStart: 0.45, flowerEnd: 0.65, flowerColor: "#7aa8e8", headGreen: "#6a9a4a", headRipe: "#b08a44", stemRipe: "#c8a860", leafRipe: "#c0a050" },
    CAMELINA: { label: "Camelina", group: "US", form: "stalk", stems: 3, spread: 0.3, density: 22, height: 0.55, stemWidth: 0.004, stemNodes: false, stemShow: 0.3, leafShape: "broad", leafLength: 0.06, leafWidth: 0.3, leafCount: 7, leafTo: 0.85, leafDroop: 0.2, leafDrop: 0.8, head: "raceme", headLen: 0.1, headCount: 9, headStart: 0.45, flowerStart: 0.45, flowerEnd: 0.65, flowerColor: "#ece69a", headGreen: "#8aa860", headRipe: "#b8a070", stemRipe: "#b8a070" },
    MUSTARD: { label: "Mustard", group: "US", form: "stalk", stems: 3, spread: 0.3, density: 18, height: 0.75, stemWidth: 0.005, stemNodes: false, stemShow: 0.35, leafShape: "lobed", leafLength: 0.13, leafWidth: 0.6, leafCount: 5, leafDroop: 0.3, leafDrop: 0.8, head: "raceme", headLen: 0.13, headCount: 10, headStart: 0.45, flowerStart: 0.45, flowerEnd: 0.68, flowerColor: "#f8d81a", leafGreen: "#5f8f4a", headGreen: "#7fa35a", headRipe: "#a08858", stemRipe: "#a89060" },
    BUCKWHEAT: { label: "Buckwheat", group: "US", form: "stalk", stems: 3, spread: 0.35, density: 16, height: 0.6, stemWidth: 0.005, stemNodes: true, stemShow: 0, leafShape: "heart", leafLength: 0.1, leafWidth: 0.9, leafCount: 6, leafTo: 0.9, leafDroop: 0.3, leafDrop: 0.3, head: "flowers", headW: 0.008, headCount: 10, flowerStart: 0.4, flowerEnd: 0.8, flowerColor: "#f6f0f0", stemGreen: "#9a5a4a", headGreen: "#8aa860", headRipe: "#4a3428", stemRipe: "#7a3a2a", leafRipe: "#8a5a3a" },
    TOBACCO: { label: "Tobacco", group: "US", form: "stalk", stems: 1, spread: 0.05, density: 7, height: 0.8, stemWidth: 0.012, stemNodes: false, stemShow: 0, leafShape: "broad", leafLength: 0.3, leafWidth: 0.5, leafCount: 12, leafTo: 0.95, leafDroop: 0.5, leafDrop: 0, head: "flowers", headW: 0.012, headCount: 8, flowerStart: 0.7, flowerEnd: 0.9, flowerColor: "#e8a0b8", leafGreen: "#6a9a3e", headGreen: "#7aa04a", headRipe: "#7a6a3a", leafRipe: "#c8b040", stemRipe: "#8a9a4a", ripenStart: 0.8 },

    // Beans, peas and pulses
    PINTOBEAN: { label: "Pinto Bean", group: "US", form: "bush", stems: 4, spread: 0.6, density: 12, height: 0.4, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.12, leafWidth: 0.7, leafCount: 5, leafDroop: 0.35, leafDrop: 0.8, head: "pods", headLen: 0.045, headW: 0.009, headCount: 6, nod: 1.2, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f0d8e0", headGreen: "#6e9a3e", headRipe: "#c8b070", stemRipe: "#b89a5a", leafRipe: "#c8b040", ripenStart: 0.72 },
    NAVYBEAN: { label: "Navy Bean", group: "US", form: "bush", stems: 4, spread: 0.45, density: 13, height: 0.42, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.11, leafWidth: 0.7, leafCount: 5, leafDroop: 0.3, leafDrop: 0.8, head: "pods", headLen: 0.04, headW: 0.008, headCount: 6, nod: 1.0, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f5f3ee", headGreen: "#6e9a3e", headRipe: "#d0bc84", stemRipe: "#c0a468", leafRipe: "#c8b040", ripenStart: 0.72 },
    BLACKBEAN: { label: "Black Bean", group: "US", form: "bush", stems: 4, spread: 0.45, density: 13, height: 0.45, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.11, leafWidth: 0.7, leafCount: 5, leafDroop: 0.3, leafDrop: 0.8, head: "pods", headLen: 0.042, headW: 0.008, headCount: 6, nod: 1.0, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#b890d0", headGreen: "#6e9a3e", headRipe: "#8a6a48", stemRipe: "#9a7a50", leafRipe: "#c8b040", ripenStart: 0.72 },
    KIDNEYBEAN: { label: "Kidney Bean", group: "US", form: "bush", stems: 4, spread: 0.5, density: 12, height: 0.46, stemWidth: 0.0045, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.13, leafWidth: 0.7, leafCount: 5, leafDroop: 0.35, leafDrop: 0.8, head: "pods", headLen: 0.05, headW: 0.01, headCount: 5, nod: 1.1, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f0d8e0", headGreen: "#6e9a3e", headRipe: "#c0a070", stemRipe: "#b89a5a", leafRipe: "#c8b040", ripenStart: 0.72 },
    COWPEA: { label: "Cowpea / Black-eyed Pea", group: "US", form: "bush", stems: 5, spread: 0.7, density: 11, height: 0.5, stemWidth: 0.0045, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.13, leafWidth: 0.55, leafCount: 5, leafDroop: 0.3, leafDrop: 0.6, head: "pods", headLen: 0.09, headW: 0.007, headCount: 4, nod: 0.6, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#e0c8f0", headGreen: "#6e9a3e", headRipe: "#c8b27a", stemRipe: "#a89060", leafRipe: "#b8a050", ripenStart: 0.75 },
    CHICKPEA: { label: "Chickpea", group: "US", form: "bush", stems: 5, spread: 0.55, density: 14, height: 0.42, stemWidth: 0.0035, stemNodes: false, stemShow: 0, leafShape: "pinnate", leaflets: 6, leafLength: 0.08, leafWidth: 0.6, leafCount: 7, leafDroop: 0.25, leafDrop: 0.5, head: "pods", headLen: 0.022, headW: 0.014, headCount: 8, nod: 0.6, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f3eef6", leafGreen: "#6a8f6a", stemGreen: "#6a8f6a", headGreen: "#7a9f6a", headRipe: "#c8b080", stemRipe: "#c0a878", leafRipe: "#c0a870" },
    LENTIL: { label: "Lentil", group: "US", form: "bush", stems: 6, spread: 0.6, density: 16, height: 0.32, stemWidth: 0.003, stemNodes: false, stemShow: 0, leafShape: "pinnate", leaflets: 5, leafLength: 0.07, leafWidth: 0.4, leafCount: 7, leafDroop: 0.25, leafDrop: 0.5, head: "pods", headLen: 0.018, headW: 0.01, headCount: 8, nod: 0.6, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#dfe6f6", leafGreen: "#6a9a5a", headGreen: "#7a9f5a", headRipe: "#c8b27a", stemRipe: "#c0a870", leafRipe: "#c0a870" },
    DRYPEA: { label: "Dry Field Pea", group: "US", form: "vine", stems: 5, spread: 0.9, density: 12, height: 0.4, stemWidth: 0.003, stemNodes: false, stemShow: 0, leafShape: "pinnate", leaflets: 2, leafLength: 0.1, leafWidth: 0.6, leafCount: 6, leafDroop: 0.2, leafDrop: 0.4, head: "pods", headLen: 0.05, headW: 0.014, headCount: 5, nod: 2.2, flowerStart: 0.45, flowerEnd: 0.62, flowerColor: "#f5f3ee", leafGreen: "#6f9a6a", stemGreen: "#78a070", headGreen: "#78a650", headRipe: "#cdb886", stemRipe: "#c2aa78", leafRipe: "#c2aa72" },

    // Forage
    ALFALFA: { label: "Alfalfa", group: "US", form: "bush", stems: 6, spread: 0.35, density: 20, height: 0.55, stemWidth: 0.003, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.06, leafWidth: 0.45, leafCount: 9, leafDroop: 0.15, leafDrop: 0, head: "flowers", headW: 0.007, headCount: 6, flowerStart: 0.8, flowerEnd: 1, flowerColor: "#9a70c8", leafGreen: "#4f8a3a", headGreen: "#4f8a3a", ripenStart: 1 },
    CLOVER: { label: "Red Clover", group: "US", form: "bush", stems: 5, spread: 0.6, density: 18, height: 0.36, stemWidth: 0.003, stemNodes: false, stemShow: 0, leafShape: "trifoliate", leafLength: 0.09, leafWidth: 0.7, leafCount: 5, leafDroop: 0.2, leafDrop: 0, head: "flowers", headW: 0.014, headCount: 2, flowerStart: 0.7, flowerEnd: 1, flowerColor: "#d85a8a", leafGreen: "#4f8a3a", headGreen: "#4f8a3a", veinColor: "#b8d8a0", ripenStart: 1 },
    PEPPERMINT: { label: "Peppermint", group: "US", form: "stalk", stems: 4, spread: 0.3, density: 20, height: 0.5, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "broad", leafLength: 0.07, leafWidth: 0.55, leafCount: 10, leafTo: 0.95, leafDroop: 0.2, leafDrop: 0, head: "flowers", headW: 0.007, headCount: 6, flowerStart: 0.8, flowerEnd: 1, flowerColor: "#c0a0d8", leafGreen: "#3f6f34", headGreen: "#3f6f34", ripenStart: 1 },

    // Vegetables and ground crops
    ONION: { label: "Dry Onion", group: "US", form: "rosette", density: 18, height: 0.35, leafShape: "tubular", leafLength: 0.32, leafWidth: 0.05, leafCount: 7, leafDroop: 0.2, leafDrop: 0, head: "none", leafGreen: "#5f8f7a", leafRipe: "#b89a60", ripenStart: 0.8 },
    GARLIC: { label: "Garlic", group: "US", form: "rosette", density: 18, height: 0.38, leafShape: "strap", leafLength: 0.3, leafWidth: 0.07, leafCount: 8, leafDroop: 0.35, leafDrop: 0, head: "none", leafGreen: "#5f8f78", leafRipe: "#b8a060", ripenStart: 0.8 },
    LETTUCE: { label: "Lettuce", group: "US", form: "rosette", density: 12, height: 0.2, leafShape: "broad", leafLength: 0.14, leafWidth: 0.85, leafCount: 14, leafDroop: 0.3, leafDrop: 0, head: "none", leafGreen: "#6fae3e", veinColor: "#d8f0b0", ripenStart: 1 },
    CABBAGE: { label: "Cabbage", group: "US", form: "rosette", density: 9, height: 0.26, leafShape: "broad", leafLength: 0.2, leafWidth: 0.95, leafCount: 12, leafDroop: 0.5, leafDrop: 0, head: "none", leafGreen: "#5f8f7a", veinColor: "#d0e4d0", ripenStart: 1 },
    PEANUT: { label: "Peanut", group: "US", form: "vine", stems: 6, spread: 1.0, density: 12, height: 0.32, stemWidth: 0.004, stemNodes: false, stemShow: 1.1, leafShape: "pinnate", leaflets: 2, leafLength: 0.11, leafWidth: 0.6, leafCount: 9, leafDroop: 0.15, leafDrop: 0.1, head: "flowers", headW: 0.008, headCount: 3, flowerStart: 0.35, flowerEnd: 0.7, flowerColor: "#f6c81a", leafGreen: "#4f8a3a", headGreen: "#4f8a3a", leafRipe: "#9aa040", ripenStart: 0.85 },
    SWEETPOTATO: { label: "Sweet Potato", group: "US", form: "vine", stems: 6, spread: 1.2, density: 8, height: 0.28, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "heart", leafLength: 0.11, leafWidth: 0.9, leafCount: 8, leafDroop: 0.15, leafDrop: 0, head: "none", leafGreen: "#4f8a3a", stemGreen: "#7a5a6a", veinColor: "#8a5a7a", ripenStart: 1 },
    PUMPKIN: { label: "Pumpkin", group: "US", form: "vine", stems: 4, spread: 1.3, density: 5, height: 0.3, stemWidth: 0.006, stemNodes: false, stemShow: 0, leafShape: "lobed", leafLength: 0.2, leafWidth: 1.0, leafCount: 6, leafDroop: 0.15, leafDrop: 0.7, head: "fruit", headW: 0.07, headCount: 1, flowerStart: 0.4, flowerEnd: 0.58, flowerColor: "#f3b21a", leafGreen: "#4f7f34", headGreen: "#5a7a34", headRipe: "#e07818", leafRipe: "#8a7a44", stemRipe: "#8a8a4a", ripenStart: 0.7 },
    WATERMELON: { label: "Watermelon", group: "US", form: "vine", stems: 5, spread: 1.3, density: 6, height: 0.26, stemWidth: 0.004, stemNodes: false, stemShow: 0, leafShape: "palmate", leafLength: 0.12, leafWidth: 0.3, leafCount: 7, leafDroop: 0.15, leafDrop: 0, head: "fruit", headW: 0.06, headCount: 1, flowerStart: 0.4, flowerEnd: 0.58, flowerColor: "#f3d21a", leafGreen: "#5a8a4a", headGreen: "#3f7034", headRipe: "#2f5a2a", ripenStart: 1 },
    TOMATO: { label: "Processing Tomato", group: "US", form: "bush", stems: 5, spread: 0.9, density: 8, height: 0.42, stemWidth: 0.005, stemNodes: false, stemShow: 0, leafShape: "pinnate", leaflets: 3, leafLength: 0.14, leafWidth: 0.55, leafCount: 6, leafDroop: 0.4, leafDrop: 0.3, head: "fruit", headW: 0.022, headCount: 5, flowerStart: 0.4, flowerEnd: 0.6, flowerColor: "#f3d21a", leafGreen: "#4f7f34", headGreen: "#6a9a3e", headRipe: "#d8301a", leafRipe: "#8a8a40", ripenStart: 0.7 },
    CHILEPEPPER: { label: "Chile Pepper", group: "US", form: "bush", stems: 4, spread: 0.5, density: 10, height: 0.45, stemWidth: 0.005, stemNodes: false, stemShow: 0, leafShape: "broad", leafLength: 0.09, leafWidth: 0.45, leafCount: 8, leafDroop: 0.3, leafDrop: 0.1, head: "pods", headLen: 0.05, headW: 0.014, headCount: 5, nod: 2.6, flowerStart: 0.4, flowerEnd: 0.6, flowerColor: "#f5f3ee", leafGreen: "#3f7034", headGreen: "#3f8a2a", headRipe: "#c8201a", ripenStart: 0.75 },
    PIMACOTTON: { label: "Pima Cotton", group: "US", form: "bush", stems: 4, spread: 0.4, density: 9, height: 0.72, stemWidth: 0.006, stemNodes: false, stemShow: 0, leafShape: "lobed", leafLength: 0.13, leafWidth: 0.75, leafCount: 6, leafDroop: 0.25, leafDrop: 0.85, head: "bolls", headW: 0.03, headCount: 5, flowerStart: 0.45, flowerEnd: 0.6, flowerColor: "#f6e27a", headGreen: "#6e9440", headRipe: "#fbf6e8", stemRipe: "#6a4a30", leafRipe: "#7a4a2a", ripenStart: 0.7 }
  };

  function getPreset(key) {
    const preset = PLANT_PRESETS[key];
    return preset ? { ...DEFAULT_DESIGN, ...preset, preset: key } : null;
  }

  function normalizeDesign(design) {
    return { ...DEFAULT_DESIGN, ...(design || {}) };
  }

  // ---------------------------------------------------------------------------
  // Leaves
  // ---------------------------------------------------------------------------

  function fillBlade(ctx, len, w, shape, color, veinColor, px) {
    const grad = ctx.createLinearGradient(-w / 2, 0, w / 2, 0);
    grad.addColorStop(0, shadeHex(color, 0.14));
    grad.addColorStop(0.5, color);
    grad.addColorStop(1, shadeHex(color, -0.22));
    ctx.fillStyle = grad;
    ctx.beginPath();
    if (shape === "heart") {
      ctx.moveTo(0, -len * 0.05);
      ctx.bezierCurveTo(w * 0.3, len * 0.1, w * 0.62, 0, w * 0.52, -len * 0.38);
      ctx.bezierCurveTo(w * 0.42, -len * 0.72, w * 0.12, -len * 0.9, 0, -len);
      ctx.bezierCurveTo(-w * 0.12, -len * 0.9, -w * 0.42, -len * 0.72, -w * 0.52, -len * 0.38);
      ctx.bezierCurveTo(-w * 0.62, 0, -w * 0.3, len * 0.1, 0, -len * 0.05);
    } else {
      ctx.moveTo(0, 0);
      ctx.bezierCurveTo(w * 0.62, -len * 0.08, w * 0.55, -len * 0.72, 0, -len);
      ctx.bezierCurveTo(-w * 0.55, -len * 0.72, -w * 0.62, -len * 0.08, 0, 0);
    }
    ctx.fill();
    const vein = veinColor || shadeHex(color, 0.28);
    withAlpha(ctx, veinColor ? 0.85 : 0.45, () => {
      ctx.strokeStyle = vein;
      ctx.lineWidth = Math.max(0.4, Math.min(w * 0.05, 1.6 * px));
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -len * 0.92);
      ctx.stroke();
      ctx.lineWidth *= 0.55;
      for (let i = 1; i <= 3; i++) {
        const y = -len * (0.2 + i * 0.18);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w * 0.32, y - len * 0.14);
        ctx.moveTo(0, y);
        ctx.lineTo(-w * 0.32, y - len * 0.14);
        ctx.stroke();
      }
    });
  }

  function drawStrap(ctx, base, angle, len, w, color, droop, rng, px, tubular) {
    const [p0, p1, p2] = droopCurve(base, angle, len, droop);
    const grad = ctx.createLinearGradient(p0.x, p0.y, p2.x, p2.y);
    grad.addColorStop(0, shadeHex(color, -0.08));
    grad.addColorStop(0.6, color);
    grad.addColorStop(1, shadeHex(color, 0.05));
    const phase = rng() * Math.PI;
    const freq = 1 + rng() * 3;
    drawRibbon(ctx, p0, p1, p2, (t) => {
      if (tubular) {
        return w * (t > 0.85 ? Math.sqrt((1 - t) / 0.15) : 1);
      }
      const profile = t < 0.12 ? 0.55 + t * 3.7 : Math.pow((1 - t) / 0.88, 0.8);
      // Cereal leaves twist along their length, so the visible width pinches in places.
      const twist = w / len < 0.06 ? 0.7 : 0.25;
      return w * profile * (1 - twist + twist * Math.abs(Math.cos(phase + t * freq)));
    }, grad);
    withAlpha(ctx, tubular ? 0.5 : 0.35, () => {
      strokeQuad(ctx, { x: p0.x - w * 0.15, y: p0.y }, { x: p1.x - w * 0.15, y: p1.y }, p2, shadeHex(color, 0.3), Math.max(0.3, w * (tubular ? 0.2 : 0.12)), 0.02, 0.8);
    });
  }

  function drawPetiole(ctx, base, angle, len, color, px, droop = 0.15) {
    const [p0, p1, p2] = droopCurve(base, angle, len, droop);
    strokeQuad(ctx, p0, p1, p2, shadeHex(color, 0.05), Math.max(0.6, 1.3 * px));
    return { end: p2, angle: quadAngle(p0, p1, p2, 1) };
  }

  // Draws one leaf of the given shape attached at base, pointing along angle.
  function drawLeaf(ctx, shape, base, angle, len, widthRatio, color, opts) {
    const { droop, rng, px, veinColor, leaflets } = opts;
    const foreshorten = 0.35 + rng() * 0.65;
    const side = Math.sin(angle) >= 0 ? 1 : -1;
    const bladeAngle = (a) => a + side * droop * 0.9;

    switch (shape) {
      case "strap":
        drawStrap(ctx, base, angle, len, len * widthRatio, color, droop, rng, px, false);
        return;
      case "tubular":
        drawStrap(ctx, base, angle, len, len * widthRatio, color, droop * 0.5, rng, px, true);
        return;
      case "broad":
      case "heart": {
        const pet = drawPetiole(ctx, base, angle, len * 0.25, color, px);
        const bl = len * 0.78;
        inLocalFrame(ctx, pet.end, bladeAngle(pet.angle), () => fillBlade(ctx, bl, bl * widthRatio, shape, color, veinColor, px), foreshorten);
        return;
      }
      case "trifoliate": {
        const pet = drawPetiole(ctx, base, angle, len * 0.38, color, px);
        const bl = len * 0.5;
        const a = bladeAngle(pet.angle);
        [-0.95, 0.95, 0].forEach((off) => {
          const l = off === 0 ? bl : bl * 0.82;
          inLocalFrame(ctx, pet.end, a + off, () => fillBlade(ctx, l, l * widthRatio, "broad", shadeHex(color, off * 0.05), veinColor, px), 0.45 + rng() * 0.55);
        });
        return;
      }
      case "pinnate": {
        const [p0, p1, p2] = droopCurve(base, angle, len, droop * 0.6);
        strokeQuad(ctx, p0, p1, p2, shadeHex(color, 0.05), Math.max(0.6, 1.1 * px));
        const pairs = Math.max(1, Math.round(leaflets || 3));
        const ll = len * (0.32 - Math.min(0.12, pairs * 0.02));
        for (let i = 0; i < pairs; i++) {
          const t = 0.3 + (i / pairs) * 0.6;
          const p = quadPoint(p0, p1, p2, t);
          const ra = quadAngle(p0, p1, p2, t);
          [-1, 1].forEach((s) => {
            inLocalFrame(ctx, p, ra + s * (0.9 + rng() * 0.3), () => fillBlade(ctx, ll, ll * widthRatio, "broad", shadeHex(color, (rng() - 0.5) * 0.1), veinColor, px), 0.5 + rng() * 0.5);
          });
        }
        inLocalFrame(ctx, p2, quadAngle(p0, p1, p2, 1), () => fillBlade(ctx, ll * 1.1, ll * 1.1 * widthRatio, "broad", color, veinColor, px), foreshorten);
        return;
      }
      case "feathery": {
        const [p0, p1, p2] = droopCurve(base, angle, len, droop * 0.7);
        strokeQuad(ctx, p0, p1, p2, shadeHex(color, 0.08), Math.max(0.6, 1.2 * px));
        ctx.lineCap = "round";
        const branches = 9;
        for (let i = 0; i < branches; i++) {
          const t = 0.25 + (i / branches) * 0.72;
          const p = quadPoint(p0, p1, p2, t);
          const ra = quadAngle(p0, p1, p2, t);
          [-1, 1].forEach((s) => {
            const bl = len * 0.22 * (1 - t * 0.6) * (0.7 + rng() * 0.5) * (0.6 + widthRatio);
            const ba = ra + s * (0.7 + rng() * 0.4);
            const bEnd = dirPoint(p, ba, bl);
            ctx.strokeStyle = shadeHex(color, (rng() - 0.5) * 0.14);
            ctx.lineWidth = Math.max(0.5, 0.9 * px);
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(bEnd.x, bEnd.y);
            ctx.stroke();
            for (let k = 1; k <= 3; k++) {
              const sp = { x: p.x + (bEnd.x - p.x) * (k / 3.5), y: p.y + (bEnd.y - p.y) * (k / 3.5) };
              [-1, 1].forEach((s2) => {
                const tip = dirPoint(sp, ba + s2 * 0.8, bl * 0.28);
                ctx.lineWidth = Math.max(0.4, 0.7 * px);
                ctx.beginPath();
                ctx.moveTo(sp.x, sp.y);
                ctx.lineTo(tip.x, tip.y);
                ctx.stroke();
              });
            }
          });
        }
        return;
      }
      case "palmate": {
        const pet = drawPetiole(ctx, base, angle, len * 0.35, color, px);
        const a = bladeAngle(pet.angle);
        const count = 7;
        for (let i = 0; i < count; i++) {
          const off = (i / (count - 1) - 0.5) * 2.3;
          const l = len * 0.6 * (1 - Math.abs(off) * 0.28);
          inLocalFrame(ctx, pet.end, a + off, () => fillBlade(ctx, l, l * widthRatio, "broad", shadeHex(color, (rng() - 0.5) * 0.1), veinColor, px), 0.6 + rng() * 0.4);
        }
        return;
      }
      case "lobed": {
        const pet = drawPetiole(ctx, base, angle, len * 0.3, color, px);
        const a = bladeAngle(pet.angle);
        const bl = len * 0.62;
        inLocalFrame(ctx, pet.end, a, () => {
          [-0.75, 0.75, -0.35, 0.35, 0].forEach((off) => {
            const l = bl * (1 - Math.abs(off) * 0.35);
            ctx.save();
            ctx.rotate(off);
            fillBlade(ctx, l, l * widthRatio * 0.7, "broad", shadeHex(color, off * 0.08), veinColor, px);
            ctx.restore();
          });
        }, foreshorten);
        return;
      }
      default:
        drawStrap(ctx, base, angle, len, len * widthRatio, color, droop, rng, px, false);
    }
  }

  // ---------------------------------------------------------------------------
  // Heads, flowers and fruit
  // ---------------------------------------------------------------------------

  // One kernel (lemma): pointed at the top, rounded at the base, lit from the left.
  function drawKernel(ctx, cx, cy, w, h, angle, color) {
    inLocalFrame(ctx, { x: cx, y: cy }, angle, () => {
      const grad = ctx.createLinearGradient(-w, 0, w, 0);
      grad.addColorStop(0, shadeHex(color, 0.22));
      grad.addColorStop(0.45, color);
      grad.addColorStop(1, shadeHex(color, -0.3));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(0, -h);
      ctx.quadraticCurveTo(w * 1.15, -h * 0.25, w * 0.55, h * 0.8);
      ctx.quadraticCurveTo(0, h * 1.05, -w * 0.55, h * 0.8);
      ctx.quadraticCurveTo(-w * 1.15, -h * 0.25, 0, -h);
      ctx.fill();
      withAlpha(ctx, 0.5, () => {
        ctx.strokeStyle = shadeHex(color, -0.35);
        ctx.lineWidth = Math.max(0.3, w * 0.12);
        ctx.beginPath();
        ctx.moveTo(w * 0.1, -h * 0.7);
        ctx.quadraticCurveTo(w * 0.25, 0, w * 0.05, h * 0.75);
        ctx.stroke();
      });
    });
  }

  function drawFlower(ctx, p, r, color, rng, petals = 5) {
    const rot = rng() * Math.PI;
    ctx.fillStyle = color;
    for (let i = 0; i < petals; i++) {
      const a = rot + (i / petals) * Math.PI * 2;
      ctx.beginPath();
      ctx.ellipse(p.x + Math.cos(a) * r * 0.55, p.y + Math.sin(a) * r * 0.55, r * 0.55, r * 0.32, a, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = shadeHex(color === "#f2e04a" ? "#c08a20" : "#e8c030", -0.1);
    ctx.beginPath();
    ctx.arc(p.x, p.y, r * 0.25, 0, Math.PI * 2);
    ctx.fill();
  }

  // Spike or panicle in a local frame where the head grows along -y from the origin.
  function drawGrainHead(ctx, d, H, headColor, awnColor, px, rng, ripen) {
    const L = d.headLen * H * (0.85 + rng() * 0.3);
    const w = d.headW * H;
    const n = Math.max(3, Math.round(d.spikelets));

    if (d.head === "panicle") {
      for (let i = 0; i < n; i++) {
        const t = 0.08 + (i / n) * 0.92;
        const s = i % 2 === 0 ? 1 : -1;
        const reach = w * (1 - t * 0.6) * (0.6 + rng() * 0.5);
        const from = { x: 0, y: -L * t };
        const tip = { x: s * reach, y: -L * t + reach * 0.9 };
        strokeQuad(ctx, from, { x: s * reach * 0.6, y: -L * t - reach * 0.2 }, tip, shadeHex(headColor, -0.25), Math.max(0.4, 0.5 * px));
        drawKernel(ctx, tip.x, tip.y + w * 0.22, w * 0.13, w * 0.3, Math.PI + s * 0.25, shadeHex(headColor, (rng() - 0.5) * 0.15));
      }
      strokeQuad(ctx, { x: 0, y: 0 }, { x: 0, y: -L * 0.5 }, { x: 0, y: -L }, shadeHex(headColor, -0.2), Math.max(0.5, 0.8 * px));
      return;
    }

    const step = L / n;
    const kw = w * 0.23;
    const kh = step * 0.95;
    const rowOffsets = Number(d.rows) === 3 ? [-1, 1, 0] : [-1, 1];
    if (d.awn > 0) {
      ctx.lineCap = "round";
      for (let i = 0; i < n; i++) {
        const y = -i * step - kh * 0.9;
        rowOffsets.forEach((s) => {
          const awnLen = L * d.awn * (0.8 + rng() * 0.35) * (0.75 + 0.25 * (i / n));
          // Awns splay outward as the head dries.
          const spread = (s * d.awnSpread + (rng() - 0.5) * 0.05) * (1 + ripen * 1.8);
          const start = { x: s * w * 0.28, y };
          const end = { x: start.x + Math.sin(spread) * awnLen, y: y - Math.cos(spread) * awnLen };
          const bend = { x: (start.x + end.x) / 2 + s * awnLen * 0.04 * (0.5 + ripen), y: (start.y + end.y) / 2 };
          withAlpha(ctx, 0.85, () => strokeQuad(ctx, start, bend, end, shadeHex(awnColor, (rng() - 0.5) * 0.2 + (s < 0 ? 0.06 : -0.06)), Math.max(0.35, 0.5 * px)));
        });
      }
    }
    for (let i = 0; i < n; i++) {
      const y = -i * step - step * 0.5;
      const taper = i >= n - 2 ? 0.7 : i === 0 ? 0.85 : 1;
      rowOffsets.forEach((s) => {
        const c = shadeHex(headColor, s < 0 ? 0.05 : s > 0 ? -0.1 : 0.02);
        drawKernel(ctx, s * w * 0.22 * taper, y + (s === 0 ? step * 0.35 : 0), kw * taper * (s === 0 ? 1.1 : 0.9), kh * taper, s * 0.28, shadeHex(c, (rng() - 0.5) * 0.08));
      });
    }
  }

  function drawTassel(ctx, d, H, color, px, rng) {
    const L = d.headLen * H;
    ctx.lineCap = "round";
    const branches = 6 + Math.floor(rng() * 4);
    for (let i = 0; i < branches; i++) {
      const t = 0.1 + (i / branches) * 0.5;
      const s = i % 2 === 0 ? 1 : -1;
      const from = { x: 0, y: -L * t };
      const bl = L * (0.55 + rng() * 0.3) * (1 - t * 0.5);
      const a = s * (0.35 + rng() * 0.5);
      const end = dirPoint(dirPoint(from, a, bl * 0.5), a + s * 0.5, bl * 0.5);
      strokeQuad(ctx, from, dirPoint(from, a, bl * 0.5), end, shadeHex(color, (rng() - 0.5) * 0.15), Math.max(0.6, 1.1 * px));
    }
    strokeQuad(ctx, { x: 0, y: 0 }, { x: 0, y: -L * 0.5 }, { x: (rng() - 0.5) * L * 0.1, y: -L }, color, Math.max(0.8, 1.5 * px));
  }

  function drawEar(ctx, d, H, huskColor, silkColor, px, ripen) {
    const L = d.headLen * H * 1.3;
    const w = d.headW * H;
    const grad = ctx.createLinearGradient(-w / 2, 0, w / 2, 0);
    grad.addColorStop(0, shadeHex(huskColor, 0.15));
    grad.addColorStop(1, shadeHex(huskColor, -0.25));
    drawRibbon(ctx, { x: 0, y: 0 }, { x: w * 0.2, y: -L * 0.5 }, { x: 0, y: -L }, (t) => w * Math.sin(Math.PI * Math.min(1, 0.1 + t * 0.95)) * (t > 0.8 ? 0.8 : 1), grad);
    withAlpha(ctx, 0.35, () => {
      strokeQuad(ctx, { x: -w * 0.1, y: -L * 0.05 }, { x: w * 0.05, y: -L * 0.5 }, { x: 0, y: -L * 0.95 }, shadeHex(huskColor, -0.3), Math.max(0.4, 0.6 * px));
    });
    if (ripen < 0.5) {
      withAlpha(ctx, 1 - ripen * 2, () => {
        for (let i = 0; i < 6; i++) {
          const a = (i - 2.5) * 0.18;
          strokeQuad(ctx, { x: 0, y: -L }, dirPoint({ x: 0, y: -L }, a, L * 0.12), dirPoint({ x: 0, y: -L }, a * 2.2, L * 0.24), silkColor, Math.max(0.4, 0.6 * px));
        }
      });
    }
  }

  function drawDisc(ctx, d, H, st, colors, px, rng) {
    const r = d.headW * H * 0.5 * (0.85 + rng() * 0.3);
    const { flowering, ripen, bud } = st;
    if (bud) {
      ctx.fillStyle = colors.headGreen;
      for (let i = 0; i < 10; i++) {
        const a = (i / 10) * Math.PI * 2;
        ctx.beginPath();
        ctx.ellipse(Math.cos(a) * r * 0.35, Math.sin(a) * r * 0.2, r * 0.3, r * 0.1, a, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.beginPath();
      ctx.ellipse(0, 0, r * 0.35, r * 0.25, 0, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    // The head is seen slightly from the side; y is squashed.
    const sq = 0.45 + rng() * 0.25;
    if (flowering > 0) {
      const petals = 22;
      for (let i = 0; i < petals; i++) {
        const a = (i / petals) * Math.PI * 2;
        const pr = r * (1.45 - ripen * 0.6);
        ctx.fillStyle = shadeHex(lerpHex(colors.flower, "#8a6a30", ripen), (rng() - 0.5) * 0.15);
        withAlpha(ctx, flowering, () => {
          ctx.beginPath();
          ctx.ellipse(Math.cos(a) * pr * 0.72, Math.sin(a) * pr * 0.72 * sq, pr * 0.34, pr * 0.1, a, 0, Math.PI * 2);
          ctx.fill();
        });
      }
    }
    // Back of the head (bracts) shows when it nods over.
    const back = lerpHex(colors.headGreen, colors.headRipe, ripen);
    const faceColor = lerpHex("#5a3a1a", "#3a2a1a", ripen);
    const grad = ctx.createRadialGradient(-r * 0.3, -r * 0.2 * sq, r * 0.1, 0, 0, r);
    grad.addColorStop(0, shadeHex(ripen > 0.6 ? back : faceColor, 0.15));
    grad.addColorStop(1, shadeHex(ripen > 0.6 ? back : faceColor, -0.25));
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(0, 0, r, r * sq, 0, 0, Math.PI * 2);
    ctx.fill();
    withAlpha(ctx, 0.35, () => {
      ctx.fillStyle = shadeHex(faceColor, 0.25);
      for (let i = 0; i < 40; i++) {
        const a = rng() * Math.PI * 2;
        const rr = Math.sqrt(rng()) * r * 0.85;
        ctx.fillRect(Math.cos(a) * rr, Math.sin(a) * rr * sq, px * 1.2, px * 1.2);
      }
    });
  }

  function drawRacemeTop(ctx, top, stemAngle, d, H, st, colors, px, rng) {
    const branches = 3 + Math.floor(rng() * 2);
    const L = d.headLen * H;
    for (let b = 0; b < branches; b++) {
      const a = stemAngle + (b / (branches - 1) - 0.5) * 0.9 + (rng() - 0.5) * 0.2;
      const bl = L * (0.6 + rng() * 0.5);
      const end = dirPoint(top, a, bl);
      strokeQuad(ctx, top, dirPoint(top, a * 0.6, bl * 0.5), end, colors.stem, Math.max(0.6, 1 * px));
      const count = Math.max(3, Math.round(d.headCount));
      for (let i = 0; i < count; i++) {
        const t = 0.35 + (i / count) * 0.65;
        const p = quadPoint(top, dirPoint(top, a * 0.6, bl * 0.5), end, t);
        const s = i % 2 === 0 ? 1 : -1;
        // Flowers open from the bottom of the raceme up; below them the pods (siliques) form.
        const openAt = st.flowerPhase * 1.3 - (1 - t);
        if (st.flowering > 0 && openAt > 0 && openAt < 0.9 && st.ripen < 0.2) {
          drawFlower(ctx, dirPoint(p, a + s * 0.6, H * 0.006), H * 0.008, colors.flower, rng, 4);
        } else if (st.podding > 0 && openAt >= 0.9) {
          const podEnd = dirPoint(p, a + s * 0.45, H * 0.03 * st.podding);
          strokeQuad(ctx, p, dirPoint(p, a + s * 0.3, H * 0.015), podEnd, colors.head, Math.max(0.6, 1.3 * px));
        }
      }
      if (st.flowering > 0 && st.ripen < 0.2) {
        withAlpha(ctx, st.flowering, () => drawFlower(ctx, end, H * 0.01, colors.flower, rng, 4));
      }
    }
  }

  function drawPod(ctx, p, angle, d, H, color, px, rng) {
    const L = d.headLen * H * (0.7 + rng() * 0.5);
    const w = Math.max(1.2 * px, d.headW * H);
    const bend = (rng() - 0.5) * 0.6;
    const end = dirPoint(dirPoint(p, angle, L * 0.5), angle + bend, L * 0.5);
    const grad = ctx.createLinearGradient(p.x - w, p.y, p.x + w, p.y);
    grad.addColorStop(0, shadeHex(color, 0.15));
    grad.addColorStop(1, shadeHex(color, -0.2));
    drawRibbon(ctx, p, dirPoint(p, angle, L * 0.5), end, (t) => w * Math.min(1, Math.sin(Math.PI * t) * 1.6), grad);
  }

  function drawBoll(ctx, p, d, H, st, colors, px, rng) {
    const r = d.headW * H * 0.5 * (0.8 + rng() * 0.4);
    if (st.ripen > 0.3) {
      const open = clamp01((st.ripen - 0.3) / 0.4);
      ctx.fillStyle = shadeHex("#5a3a22", -0.1);
      for (let i = 0; i < 4; i++) {
        const a = (i / 4) * Math.PI * 2 + 0.4;
        ctx.beginPath();
        ctx.ellipse(p.x + Math.cos(a) * r * 0.6, p.y + Math.sin(a) * r * 0.6 + r * 0.3, r * 0.45, r * 0.15, a, 0, Math.PI * 2);
        ctx.fill();
      }
      for (let i = 0; i < 5; i++) {
        const a = (i / 5) * Math.PI * 2;
        const lr = r * (0.45 + open * 0.25);
        const c = { x: p.x + Math.cos(a) * r * 0.45 * open, y: p.y + Math.sin(a) * r * 0.4 * open };
        const grad = ctx.createRadialGradient(c.x - lr * 0.3, c.y - lr * 0.3, lr * 0.1, c.x, c.y, lr);
        grad.addColorStop(0, "#ffffff");
        grad.addColorStop(1, shadeHex(colors.headRipe, -0.12));
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(c.x, c.y, lr, 0, Math.PI * 2);
        ctx.fill();
      }
      return;
    }
    const grad = ctx.createRadialGradient(p.x - r * 0.3, p.y - r * 0.3, r * 0.1, p.x, p.y, r);
    grad.addColorStop(0, shadeHex(colors.headGreen, 0.2));
    grad.addColorStop(1, shadeHex(colors.headGreen, -0.25));
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, r * 0.75, r, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  // Round fruit (pumpkin, melon, tomato) with ribs and a highlight.
  function drawFruit(ctx, p, d, H, color, px, rng) {
    const r = d.headW * H * 0.5 * (0.8 + rng() * 0.4);
    const squash = 0.75 + rng() * 0.2;
    const grad = ctx.createRadialGradient(p.x - r * 0.35, p.y - r * 0.35 * squash, r * 0.1, p.x, p.y, r);
    grad.addColorStop(0, shadeHex(color, 0.3));
    grad.addColorStop(0.6, color);
    grad.addColorStop(1, shadeHex(color, -0.35));
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, r, r * squash, 0, 0, Math.PI * 2);
    ctx.fill();
    if (r > 6 * px) {
      withAlpha(ctx, 0.3, () => {
        ctx.strokeStyle = shadeHex(color, -0.4);
        ctx.lineWidth = Math.max(0.5, r * 0.04);
        for (let i = -2; i <= 2; i++) {
          ctx.beginPath();
          ctx.ellipse(p.x, p.y, Math.abs(i) * r * 0.3 + r * 0.05, r * squash * 0.98, 0, 0, Math.PI * 2);
          ctx.stroke();
        }
      });
    }
    ctx.fillStyle = shadeHex("#6a5a2a", -0.1);
    ctx.fillRect(p.x - r * 0.06, p.y - r * squash - r * 0.12, r * 0.12, r * 0.18);
  }

  // ---------------------------------------------------------------------------
  // Plants
  // ---------------------------------------------------------------------------

  function stageState(d, g) {
    const flowerSpan = Math.max(0.01, d.flowerEnd - d.flowerStart);
    const flowerPhase = clamp01((g - d.flowerStart) / flowerSpan);
    const inFlower = g >= d.flowerStart && g <= d.flowerEnd + 0.05;
    return {
      g,
      ripen: d.ripenStart >= 1 ? 0 : clamp01((g - d.ripenStart) / Math.max(0.05, 1 - d.ripenStart)),
      flowerPhase,
      // Fade flowers in and out at the ends of the flowering window.
      flowering: inFlower ? Math.min(1, flowerPhase * 4, (d.flowerEnd + 0.05 - g) / 0.08) : 0,
      podding: clamp01((g - d.flowerStart - flowerSpan * 0.5) / (flowerSpan * 0.8)),
      headed: g >= d.headStart,
      emerge: clamp01((g - d.headStart) / 0.18)
    };
  }

  function drawPlant(ctx, x, d, opts) {
    const { H, px, g, st, rng, depth } = opts;
    const dark = -0.32 * (1 - depth);
    const heightScale = opts.heightScale;
    const heightGrowth = Math.min(1, 0.15 + 0.85 * (g / 0.8));
    const leafGrowth = 0.35 + 0.65 * Math.min(1, g / 0.7);
    const ripen = st.ripen;
    const colors = {
      stem: shadeHex(lerpHex(d.stemGreen, d.stemRipe, ripen), dark),
      head: shadeHex(lerpHex(lerpHex(d.headGreen, shadeHex(d.headGreen, 0.15), g), d.headRipe, ripen), dark),
      awn: shadeHex(lerpHex(lerpHex(d.headGreen, "#ffffff", 0.25), d.awnRipe, ripen), dark),
      flower: shadeHex(d.flowerColor, dark * 0.6),
      headGreen: shadeHex(d.headGreen, dark),
      headRipe: shadeHex(d.headRipe, dark)
    };

    const form = d.form;
    const heightVar = 0.78 + rng() * 0.27;
    const plantH = H * d.height * heightGrowth * heightVar * heightScale;
    const stemCount = form === "rosette" ? 1 : Math.max(1, Math.round(d.stems * (0.5 + 0.5 * Math.min(1, g / 0.5)) + (rng() - 0.5)));
    const leafCountBase = Math.max(1, Math.round(d.leafCount * (0.4 + 0.6 * Math.min(1, g / 0.6)) * (1 - ripen * d.leafDrop)));

    for (let s = 0; s < stemCount; s++) {
      const fan = stemCount > 1 ? (s / (stemCount - 1) - 0.5) * 2 : 0;
      let lean = fan * d.spread + (rng() - 0.5) * Math.min(0.3, d.spread + 0.1);
      let h = plantH * (0.88 + rng() * 0.17);
      if (form === "vine") {
        lean = (fan >= 0 ? 1 : -1) * (0.9 + rng() * 0.5) * Math.min(1.4, d.spread + 0.4);
        h = plantH * (1.4 + rng() * 0.6);
      } else if (form === "bush") {
        h *= 1 - Math.abs(fan) * 0.25;
      }
      const base = { x: x + (rng() - 0.5) * 8 * px, y: H + 2 * px };
      let top;
      let ctrl;
      if (form === "vine") {
        // Vines run along the ground and lift only slightly at the tips.
        top = { x: base.x + Math.sin(lean) * h, y: base.y - plantH * (0.25 + rng() * 0.25) };
        ctrl = { x: base.x + Math.sin(lean) * h * 0.5, y: base.y - plantH * 0.45 };
      } else {
        top = dirPoint(base, lean, h);
        ctrl = { x: base.x + Math.sin(lean) * h * (form === "bush" ? 0.15 : 0.25) + (rng() - 0.5) * h * 0.04, y: base.y - h * 0.5 };
      }
      const topAngle = quadAngle(base, ctrl, top, 1);

      // Stem: under the leaves on bushes and vines, over the leaf sheaths on stalk crops.
      const drawStem = () => {
        if (form === "rosette" || g < d.stemShow) {
          return;
        }
        const sw = Math.max(1, H * d.stemWidth * (0.6 + 0.4 * Math.min(1, g / 0.6)));
        drawRibbon(ctx, base, ctrl, top, (t) => sw * (1 - t * 0.35), colors.stem);
        withAlpha(ctx, 0.45, () => strokeQuad(ctx, { x: base.x - sw * 0.2, y: base.y }, { x: ctrl.x - sw * 0.2, y: ctrl.y }, { x: top.x - sw * 0.15, y: top.y }, shadeHex(colors.stem, 0.35), sw * 0.3));
        if (d.stemNodes) {
          ctx.fillStyle = shadeHex(colors.stem, -0.2);
          const nodes = d.stemWidth > 0.012 ? 8 : 3;
          for (let i = 1; i <= nodes; i++) {
            const t = (i / (nodes + 1)) * 0.85 + (rng() - 0.5) * 0.04;
            const p = quadPoint(base, ctrl, top, t);
            ctx.beginPath();
            ctx.ellipse(p.x, p.y, sw * 0.65, sw * (d.stemWidth > 0.012 ? 0.25 : 0.4), quadAngle(base, ctrl, top, t), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      };
      if (form !== "stalk") {
        drawStem();
      }

      // Leaves
      const leafCount = form === "rosette" ? Math.max(3, leafCountBase) : leafCountBase;
      for (let l = 0; l < leafCount; l++) {
        let at;
        let angle;
        let attach;
        const sideL = l % 2 === 0 ? -1 : 1;
        if (form === "rosette") {
          attach = { x: base.x + (rng() - 0.5) * 6 * px, y: base.y - 2 * px };
          angle = ((l + 0.5) / leafCount - 0.5) * 2 * (0.25 + d.leafDroop * 0.8) + (rng() - 0.5) * 0.3;
          at = 0;
        } else {
          const zone = form === "stalk" ? [d.leafFrom, d.leafTo] : [Math.max(0.1, d.leafFrom), Math.max(0.95, d.leafTo)];
          at = g < d.stemShow && form === "stalk" && d.leafFrom === 0 ? 0 : Math.min(1, zone[0] + ((l + rng() * 0.9) / leafCount) * (zone[1] - zone[0]));
          attach = quadPoint(base, ctrl, top, at);
          const stemA = quadAngle(base, ctrl, top, at);
          angle = form === "vine" ? (rng() - 0.5) * 1.2 : stemA + sideL * (0.45 + rng() * 0.6);
        }
        const dry = form === "rosette" ? ripen * 0.6 : clamp01(ripen * 1.3 + (1 - at) * g * 0.35 - 0.15);
        const leafLen = H * d.leafLength * leafGrowth * (0.65 + rng() * 0.5) * (form === "stalk" ? 1 - at * 0.45 : 1 - at * 0.25) * (1 - dry * 0.3) * heightScale;
        const light = Math.sin(angle) < 0 ? 0.05 : -0.07;
        const color = shadeHex(lerpHex(d.leafGreen, d.leafRipe, dry), dark + light + (rng() - 0.5) * 0.08);
        drawLeaf(ctx, d.leafShape, attach, angle, leafLen, d.leafWidth, color, {
          droop: clamp01(d.leafDroop * (0.6 + rng() * 0.8) + dry * 0.35),
          rng,
          px,
          veinColor: d.veinColor ? shadeHex(d.veinColor, dark) : "",
          leaflets: d.leaflets
        });
      }

      if (form === "stalk") {
        drawStem();
      }

      drawStemFruit(ctx, d, { base, ctrl, top, topAngle, lean, h, H, px, st, colors, rng, form, g });
    }
  }

  // Heads at the stem top, or pods/bolls/flowers along the stem.
  function drawStemFruit(ctx, d, o) {
    const { base, ctrl, top, topAngle, lean, h, H, px, st, colors, rng, form, g } = o;
    const head = d.head;
    if (head === "none" || !st.headed) {
      return;
    }
    const side = lean >= 0 ? 1 : -1;
    const ripen = st.ripen;

    if (head === "spike" || head === "panicle" || head === "disc" || head === "tassel") {
      if (form === "rosette") {
        return;
      }
      const nod = d.nod * (head === "disc" ? Math.max(ripen, st.flowering * 0.25) : ripen) * (0.45 + rng() * 0.75);
      const headAngle = topAngle + side * nod;
      const neckLen = h * (0.07 + 0.05 * ripen * Math.min(1, d.nod / 2));
      const nc = dirPoint(top, topAngle, neckLen);
      const hb = dirPoint(nc, headAngle, neckLen * 0.6);
      drawRibbon(ctx, top, nc, hb, () => Math.max(0.8, H * d.stemWidth * 0.75), colors.stem);
      if (head === "disc") {
        const bud = g < d.flowerStart;
        inLocalFrame(ctx, hb, headAngle, () => {
          ctx.translate(0, -d.headW * H * 0.15);
          drawDisc(ctx, d, H, { flowering: st.flowering || (g > d.flowerEnd ? 0.25 * (1 - ripen) : 0), ripen, bud }, colors, px, rng);
        });
        return;
      }
      if (head === "tassel") {
        inLocalFrame(ctx, hb, headAngle * 0.3, () => drawTassel(ctx, d, H, colors.awn, px, rng));
        // One ear per stalk, about halfway up, leaning out and drooping as it dries.
        const t = 0.5 + rng() * 0.1;
        const p = quadPoint(base, ctrl, top, t);
        const a = quadAngle(base, ctrl, top, t) + side * (0.45 + ripen * d.nod * 0.6);
        inLocalFrame(ctx, p, a, () => {
          ctx.scale(st.emerge, st.emerge);
          drawEar(ctx, d, H, colors.head, d.flowerColor, px, ripen);
        });
        return;
      }
      inLocalFrame(ctx, hb, headAngle, () => {
        ctx.scale(st.emerge, st.emerge);
        drawGrainHead(ctx, d, H, colors.head, colors.awn, px, rng, ripen);
      });
      return;
    }

    if (head === "raceme") {
      if (form !== "rosette") {
        drawRacemeTop(ctx, top, topAngle, d, H, st, colors, px, rng);
      }
      return;
    }

    // Pods, bolls and flower clusters sit along the stem at the leaf joints and at the top.
    const count = Math.max(1, Math.round(d.headCount * (0.6 + rng() * 0.6)));
    const origin = form === "rosette" ? { base, ctrl, top: dirPoint(base, lean, H * d.height * 0.8) } : { base, ctrl, top };
    for (let i = 0; i < count; i++) {
      const t = head === "flowers" ? 0.85 + (i / count) * 0.15 : 0.3 + (i / count) * 0.7;
      const p = quadPoint(origin.base, origin.ctrl, origin.top, t);
      const stemA = quadAngle(origin.base, origin.ctrl, origin.top, t);
      const s = i % 2 === 0 ? 1 : -1;
      if (head === "flowers") {
        if (st.flowering > 0) {
          withAlpha(ctx, st.flowering, () => drawFlower(ctx, dirPoint(p, stemA + s * (0.4 + rng()), H * d.headW * 1.5), H * d.headW, colors.flower, rng, 5));
        } else if (g > d.flowerEnd) {
          ctx.fillStyle = colors.head;
          ctx.beginPath();
          ctx.arc(p.x + s * H * d.headW, p.y, H * d.headW * 0.45, 0, Math.PI * 2);
          ctx.fill();
        }
        continue;
      }
      if (st.flowering > 0 && st.podding < 0.3) {
        withAlpha(ctx, st.flowering, () => drawFlower(ctx, dirPoint(p, stemA + s * 0.6, H * 0.006), H * (head === "bolls" ? 0.018 : 0.007), colors.flower, rng, 5));
        continue;
      }
      if (st.podding <= 0) {
        continue;
      }
      if (head === "pods") {
        const a = stemA + s * (0.5 + d.nod * (0.4 + rng() * 0.3));
        inLocalFrame(ctx, p, 0, () => {
          ctx.scale(st.podding, st.podding);
          drawPod(ctx, { x: 0, y: 0 }, a, d, H, colors.head, px, rng);
        });
      } else if (head === "fruit") {
        const color = lerpHex(colors.headGreen, colors.headRipe, ripen);
        // Vine fruit rests on the ground; bush fruit hangs below the stem.
        const fp = form === "vine"
          ? { x: p.x, y: H - d.headW * H * 0.4 }
          : dirPoint(p, stemA + s * 2.4, H * d.headW * 0.6);
        inLocalFrame(ctx, fp, 0, () => {
          ctx.scale(Math.max(0.2, st.podding), Math.max(0.2, st.podding));
          drawFruit(ctx, { x: 0, y: 0 }, d, H, color, px, rng);
        });
      } else if (head === "bolls") {
        drawBoll(ctx, dirPoint(p, stemA + s * 0.7, H * d.headW * 0.4), d, H, st, colors, px, rng);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Texture
  // ---------------------------------------------------------------------------

  // Shading passes applied only where plants were drawn: ground occlusion, top light and fine grain.
  function finishFoliageLayer(layer, W, H, seed, g, d) {
    const lctx = layer.getContext("2d");
    lctx.globalCompositeOperation = "source-atop";
    // Shadow reaches as high as the canopy; young plants barely shade themselves.
    const canopy = Math.min(0.9, d.height * Math.min(1, 0.15 + 0.85 * g / 0.8));
    const ao = lctx.createLinearGradient(0, H, 0, H * (1 - canopy * 0.75));
    ao.addColorStop(0, `rgba(28, 20, 8, ${(0.2 + 0.4 * g).toFixed(2)})`);
    ao.addColorStop(1, "rgba(28, 20, 8, 0)");
    lctx.fillStyle = ao;
    lctx.fillRect(0, 0, W, H);
    const sun = lctx.createLinearGradient(0, 0, 0, H * 0.55);
    sun.addColorStop(0, "rgba(255, 244, 214, 0.14)");
    sun.addColorStop(1, "rgba(255, 244, 214, 0)");
    lctx.fillStyle = sun;
    lctx.fillRect(0, 0, W, H);
    lctx.globalCompositeOperation = "source-over";

    const img = lctx.getImageData(0, 0, W, H);
    const data = img.data;
    let s = seed >>> 0 || 1;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] === 0) {
        continue;
      }
      s = (s * 1664525 + 1013904223) >>> 0;
      const n = ((s >>> 24) - 128) * 0.09;
      data[i] = Math.max(0, Math.min(255, data[i] + n));
      data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + n));
      data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + n * 0.8));
    }
    lctx.putImageData(img, 0, 0);
  }

  // Draws one growth stage of a design into canvas as a square, horizontally tiling billboard.
  function generatePlantTexture(canvas, options) {
    const {
      design,
      seedName = "CROP",
      growthStage = 4,
      maxGrowthStages = 8,
      resolution = 512,
      backgroundColor = "transparent"
    } = options;
    const d = normalizeDesign(design);
    const W = resolution;
    const H = resolution;
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, W, H);
    if (backgroundColor && backgroundColor !== "transparent") {
      ctx.fillStyle = backgroundColor;
      ctx.fillRect(0, 0, W, H);
    }

    const g = Math.max(0.05, Math.min(1, (growthStage - 1) / Math.max(1, maxGrowthStages - 1)));
    const st = stageState(d, g);
    const px = H / 512;
    const rng = makeSeedRng(hashString(String(seedName)));

    // Shrink everything if the tallest stem plus an upright head would run off the top edge.
    const upright = d.head === "spike" ? d.headLen * 1.15 * (1 + d.awn) : ["panicle", "tassel", "disc"].includes(d.head) ? d.headLen * 1.15 + d.headW * 0.6 : d.head === "raceme" ? d.headLen : 0;
    const tallest = (d.form === "rosette" ? d.leafLength * 1.2 : d.height) * 1.05 * 1.05 * 1.07;
    const heightScale = Math.min(1, (0.97 - upright) / Math.max(0.05, tallest));

    const count = Math.max(2, Math.round(d.density * (0.7 + 0.3 * g) * (W / H)));
    const plants = [];
    for (let i = 0; i < count; i++) {
      plants.push({ x: ((i + rng()) / count) * W, depth: rng(), seed: Math.floor(rng() * 0xffffffff) });
    }
    plants.sort((a, b) => a.depth - b.depth);

    const layer = document.createElement("canvas");
    layer.width = W;
    layer.height = H;
    const lctx = layer.getContext("2d");
    const margin = W * 0.35;
    plants.forEach((p) => {
      [0, -W, W].forEach((offset) => {
        const x = p.x + offset;
        if (x < -margin || x > W + margin) {
          return;
        }
        // Re-seed per plant so wrapped copies are identical and the texture tiles.
        drawPlant(lctx, x, d, { H, px, g, st, rng: makeSeedRng(p.seed), depth: p.depth, heightScale });
      });
    });
    finishFoliageLayer(layer, W, H, Math.floor(rng() * 0xffffffff), g, d);
    ctx.drawImage(layer, 0, 0);
  }

  // ---------------------------------------------------------------------------
  // Normal map
  // ---------------------------------------------------------------------------

  // Tangent-space normal map from the diffuse: height comes from coverage and brightness.
  function generateNormalMap(source, strength = 2.5) {
    const W = source.width;
    const H = source.height;
    const src = source.getContext("2d").getImageData(0, 0, W, H).data;
    const height = new Float32Array(W * H);
    for (let i = 0; i < W * H; i++) {
      const a = src[i * 4 + 3] / 255;
      const lum = (src[i * 4] * 0.3 + src[i * 4 + 1] * 0.59 + src[i * 4 + 2] * 0.11) / 255;
      height[i] = a * (0.55 + 0.45 * lum);
    }
    const out = document.createElement("canvas");
    out.width = W;
    out.height = H;
    const octx = out.getContext("2d");
    const img = octx.createImageData(W, H);
    const dst = img.data;
    const at = (x, y) => height[((y + H) % H) * W + ((x + W) % W)];
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const dx = (at(x + 1, y - 1) + 2 * at(x + 1, y) + at(x + 1, y + 1)) - (at(x - 1, y - 1) + 2 * at(x - 1, y) + at(x - 1, y + 1));
        const dy = (at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1)) - (at(x - 1, y - 1) + 2 * at(x, y - 1) + at(x + 1, y - 1));
        let nx = -dx * strength;
        let ny = dy * strength;
        let nz = 1;
        const len = Math.hypot(nx, ny, nz);
        nx /= len;
        ny /= len;
        nz /= len;
        const i = (y * W + x) * 4;
        dst[i] = Math.round((nx * 0.5 + 0.5) * 255);
        dst[i + 1] = Math.round((ny * 0.5 + 0.5) * 255);
        dst[i + 2] = Math.round((nz * 0.5 + 0.5) * 255);
        dst[i + 3] = src[i + 3];
      }
    }
    octx.putImageData(img, 0, 0);
    return out;
  }

  // ---------------------------------------------------------------------------
  // DDS export (BC1 / BC3 with mipmaps, or uncompressed BGRA)
  // ---------------------------------------------------------------------------

  // Transparent texels get the color of nearby leaves so mipmaps and filtering don't show dark fringes.
  function bleedTransparentColors(data, W, H) {
    let r = 0;
    let g = 0;
    let b = 0;
    let n = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] >= 32) {
        r += data[i];
        g += data[i + 1];
        b += data[i + 2];
        n++;
      }
    }
    const avg = n ? [r / n, g / n, b / n] : [0, 0, 0];
    const known = new Uint8Array(W * H);
    for (let i = 0; i < W * H; i++) {
      // Nearly transparent texels carry unreliable colors (un-premultiplied rounding), so replace them too.
      known[i] = data[i * 4 + 3] >= 32 ? 1 : 0;
    }
    for (let pass = 0; pass < 4; pass++) {
      const next = known.slice();
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          const i = y * W + x;
          if (known[i]) {
            continue;
          }
          let sr = 0;
          let sg = 0;
          let sb = 0;
          let c = 0;
          for (const [ox, oy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            const xx = x + ox;
            const yy = y + oy;
            if (xx < 0 || yy < 0 || xx >= W || yy >= H) {
              continue;
            }
            const j = yy * W + xx;
            if (known[j]) {
              sr += data[j * 4];
              sg += data[j * 4 + 1];
              sb += data[j * 4 + 2];
              c++;
            }
          }
          if (c) {
            data[i * 4] = sr / c;
            data[i * 4 + 1] = sg / c;
            data[i * 4 + 2] = sb / c;
            next[i] = 1;
          }
        }
      }
      known.set(next);
    }
    for (let i = 0; i < W * H; i++) {
      if (!known[i]) {
        data[i * 4] = avg[0];
        data[i * 4 + 1] = avg[1];
        data[i * 4 + 2] = avg[2];
      }
    }
  }

  function to565(r, g, b) {
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
  }

  function from565(c) {
    const r = (c >> 11) & 31;
    const g = (c >> 5) & 63;
    const b = c & 31;
    return [(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)];
  }

  // Encodes one 4x4 color block into out at offset. block is 16 RGBA texels.
  function encodeColorBlock(block, out, offset, allowTransparent) {
    let minR = 255, minG = 255, minB = 255, maxR = 0, maxG = 0, maxB = 0;
    let hasTransparent = false;
    let any = false;
    for (let i = 0; i < 16; i++) {
      const a = block[i * 4 + 3];
      if (allowTransparent && a < 128) {
        hasTransparent = true;
        continue;
      }
      if (a < 32) {
        continue;
      }
      any = true;
      const r = block[i * 4], g = block[i * 4 + 1], b = block[i * 4 + 2];
      if (r < minR) minR = r;
      if (g < minG) minG = g;
      if (b < minB) minB = b;
      if (r > maxR) maxR = r;
      if (g > maxG) maxG = g;
      if (b > maxB) maxB = b;
    }
    if (!any) {
      minR = minG = minB = maxR = maxG = maxB = 0;
    }
    // Pull the endpoints in slightly to reduce error on the extremes.
    const inset = (lo, hi) => [Math.min(255, lo + ((hi - lo) >> 4)), Math.max(0, hi - ((hi - lo) >> 4))];
    [minR, maxR] = inset(minR, maxR);
    [minG, maxG] = inset(minG, maxG);
    [minB, maxB] = inset(minB, maxB);
    let c0 = to565(maxR, maxG, maxB);
    let c1 = to565(minR, minG, minB);
    const threeColor = allowTransparent && hasTransparent;
    if (threeColor ? c0 > c1 : c0 < c1) {
      [c0, c1] = [c1, c0];
    }
    if (!threeColor && c0 === c1) {
      // Equal endpoints: every index 0 is exact.
      out[offset] = c0 & 255;
      out[offset + 1] = c0 >> 8;
      out[offset + 2] = c1 & 255;
      out[offset + 3] = c1 >> 8;
      out[offset + 4] = out[offset + 5] = out[offset + 6] = out[offset + 7] = 0;
      return;
    }
    const e0 = from565(c0);
    const e1 = from565(c1);
    const palette = threeColor
      ? [e0, e1, e0.map((v, k) => (v + e1[k]) >> 1)]
      : [e0, e1, e0.map((v, k) => (2 * v + e1[k]) / 3), e0.map((v, k) => (v + 2 * e1[k]) / 3)];
    let indices = 0;
    for (let i = 0; i < 16; i++) {
      let idx = 0;
      if (threeColor && block[i * 4 + 3] < 128) {
        idx = 3;
      } else {
        let best = Infinity;
        for (let p = 0; p < palette.length; p++) {
          const dr = block[i * 4] - palette[p][0];
          const dg = block[i * 4 + 1] - palette[p][1];
          const db = block[i * 4 + 2] - palette[p][2];
          const dist = dr * dr + dg * dg + db * db;
          if (dist < best) {
            best = dist;
            idx = p;
          }
        }
      }
      indices |= idx << (i * 2);
    }
    out[offset] = c0 & 255;
    out[offset + 1] = c0 >> 8;
    out[offset + 2] = c1 & 255;
    out[offset + 3] = c1 >> 8;
    out[offset + 4] = indices & 255;
    out[offset + 5] = (indices >>> 8) & 255;
    out[offset + 6] = (indices >>> 16) & 255;
    out[offset + 7] = (indices >>> 24) & 255;
  }

  function encodeAlphaBlock(block, out, offset) {
    let a0 = 0;
    let a1 = 255;
    for (let i = 0; i < 16; i++) {
      const a = block[i * 4 + 3];
      if (a > a0) a0 = a;
      if (a < a1) a1 = a;
    }
    out[offset] = a0;
    out[offset + 1] = a1;
    const palette = [a0, a1];
    for (let k = 1; k <= 6; k++) {
      palette.push(a0 === a1 ? a0 : Math.round(((7 - k) * a0 + k * a1) / 7));
    }
    // 16 three-bit indices, packed as two 24-bit halves (8 texels each).
    for (let half = 0; half < 2; half++) {
      let bits = 0;
      for (let k = 0; k < 8; k++) {
        const a = block[(half * 8 + k) * 4 + 3];
        let idx = 0;
        let best = Infinity;
        for (let p = 0; p < 8; p++) {
          const dist = Math.abs(a - palette[p]);
          if (dist < best) {
            best = dist;
            idx = p;
          }
        }
        bits |= idx << (k * 3);
      }
      out[offset + 2 + half * 3] = bits & 255;
      out[offset + 3 + half * 3] = (bits >> 8) & 255;
      out[offset + 4 + half * 3] = (bits >> 16) & 255;
    }
  }

  function encodeLevel(data, W, H, format) {
    if (format === "RGBA") {
      const out = new Uint8Array(W * H * 4);
      for (let i = 0; i < W * H; i++) {
        out[i * 4] = data[i * 4 + 2];
        out[i * 4 + 1] = data[i * 4 + 1];
        out[i * 4 + 2] = data[i * 4];
        out[i * 4 + 3] = data[i * 4 + 3];
      }
      return out;
    }
    const bw = Math.max(1, Math.ceil(W / 4));
    const bh = Math.max(1, Math.ceil(H / 4));
    const blockBytes = format === "BC1" ? 8 : 16;
    const out = new Uint8Array(bw * bh * blockBytes);
    const block = new Uint8Array(64);
    for (let by = 0; by < bh; by++) {
      for (let bx = 0; bx < bw; bx++) {
        for (let py = 0; py < 4; py++) {
          for (let pxl = 0; pxl < 4; pxl++) {
            const x = Math.min(W - 1, bx * 4 + pxl);
            const y = Math.min(H - 1, by * 4 + py);
            const s = (y * W + x) * 4;
            const d = (py * 4 + pxl) * 4;
            block[d] = data[s];
            block[d + 1] = data[s + 1];
            block[d + 2] = data[s + 2];
            block[d + 3] = data[s + 3];
          }
        }
        const o = (by * bw + bx) * blockBytes;
        if (format === "BC1") {
          encodeColorBlock(block, out, o, true);
        } else {
          encodeAlphaBlock(block, out, o);
          encodeColorBlock(block, out, o + 8, false);
        }
      }
    }
    return out;
  }

  // format: "BC1" (DXT1, 1-bit alpha), "BC3" (DXT5, full alpha) or "RGBA" (uncompressed).
  function encodeDds(canvas, format = "BC3", mipmaps = true) {
    const W = canvas.width;
    const H = canvas.height;
    const levels = [];
    let level = document.createElement("canvas");
    level.width = W;
    level.height = H;
    level.getContext("2d").drawImage(canvas, 0, 0);
    let w = W;
    let h = H;
    for (;;) {
      const lctx = level.getContext("2d");
      const img = lctx.getImageData(0, 0, w, h);
      bleedTransparentColors(img.data, w, h);
      levels.push(encodeLevel(img.data, w, h, format));
      if (!mipmaps || (w === 1 && h === 1)) {
        break;
      }
      // Downsample from the color-bled level so transparent edges stay clean.
      lctx.putImageData(img, 0, 0);
      const nw = Math.max(1, w >> 1);
      const nh = Math.max(1, h >> 1);
      const next = document.createElement("canvas");
      next.width = nw;
      next.height = nh;
      const nctx = next.getContext("2d");
      nctx.imageSmoothingQuality = "high";
      nctx.drawImage(level, 0, 0, w, h, 0, 0, nw, nh);
      level = next;
      w = nw;
      h = nh;
    }

    const header = new DataView(new ArrayBuffer(128));
    const u32 = (off, v) => header.setUint32(off, v >>> 0, true);
    u32(0, 0x20534444); // "DDS "
    u32(4, 124);
    const DDSD_CAPS = 0x1, DDSD_HEIGHT = 0x2, DDSD_WIDTH = 0x4, DDSD_PITCH = 0x8, DDSD_PIXELFORMAT = 0x1000, DDSD_MIPMAPCOUNT = 0x20000, DDSD_LINEARSIZE = 0x80000;
    const compressed = format !== "RGBA";
    u32(8, DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | (levels.length > 1 ? DDSD_MIPMAPCOUNT : 0) | (compressed ? DDSD_LINEARSIZE : DDSD_PITCH));
    u32(12, H);
    u32(16, W);
    u32(20, compressed ? levels[0].length : W * 4);
    u32(24, 0);
    u32(28, levels.length);
    u32(76, 32);
    if (compressed) {
      u32(80, 0x4); // DDPF_FOURCC
      u32(84, format === "BC1" ? 0x31545844 : 0x35545844); // "DXT1" / "DXT5"
    } else {
      u32(80, 0x41); // DDPF_RGB | DDPF_ALPHAPIXELS
      u32(88, 32);
      u32(92, 0x00ff0000);
      u32(96, 0x0000ff00);
      u32(100, 0x000000ff);
      u32(104, 0xff000000);
    }
    u32(108, 0x1000 | (levels.length > 1 ? 0x400008 : 0)); // TEXTURE | MIPMAP | COMPLEX
    const total = 128 + levels.reduce((sum, l) => sum + l.length, 0);
    const out = new Uint8Array(total);
    out.set(new Uint8Array(header.buffer), 0);
    let off = 128;
    levels.forEach((l) => {
      out.set(l, off);
      off += l.length;
    });
    return out;
  }

  window.CropTextures = {
    DEFAULT_DESIGN,
    PLANT_PRESETS,
    getPreset,
    normalizeDesign,
    generatePlantTexture,
    generateNormalMap,
    encodeDds,
    makeSeedRng,
    lerpHex,
    shadeHex
  };
})();
