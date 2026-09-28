# FS25_Crop-maker
A tool to create all the textures and XML needed for new Farming Simulator 25 crop types.

Open `index.html` in a browser. Nothing needs installing.

## Textures

The **Textures** tab draws a side-view foliage texture for each growth stage of a crop. The texture tiles left to right.

- **Plant Design:** pick a preset or build a crop from scratch. The settings cover plant form (stalk, bush, rosette or vine), height and stems, leaf shape, head or fruit type (spike, panicle, corn tassel and ear, sunflower disc, canola raceme, pods, cotton bolls, flowers, round fruit), when flowering and ripening happen, and colours for growing and ripe.
- **Presets:** the FS25 field crops, plus 49 US crops that aren't in the base game. See [docs/US_CROPS.md](docs/US_CROPS.md). A crop whose internal name matches a preset key (such as `DURUM` or `PEANUT`) uses that preset automatically.
- **Export:** DDS in BC3/DXT5, BC1/DXT1 or uncompressed RGBA, all with mipmaps, or PNG. There's an optional normal map. You can download one stage, or a ZIP of every stage.
- **Fill planes and windrows:** each crop gets top-down, tiling textures of its harvested material for trailers, heaps and silos. Materials are kernels, seeds, beans, tubers, roots, cotton, leaves or straw. For windrows, a crop picks a windrow fill type: `STRAW`, `GRASS_WINDROW` or `DRYGRASS_WINDROW` from the base game, or its own straw. Its own straw adds a `<FILLTYPE>_STRAW` fill type modelled on `STRAW`, with its own straw textures. Downloads include every map a fill type needs: diffuse, normal, height, displacement and distance. Height and displacement are single-channel (BC4, or 8-bit gray when uncompressed). Downloads also include a HUD icon, either a coloured heap or a flat white pictogram, and are laid out like your mod's folders. `maps_fillTypes.xml` points new crops and their straw at these files and their HUD icons. Paths use `.png`, and the game loads the `.dds` with the same name.
- **Behaves like a base crop:** each new crop follows a base-game crop (black beans → SOYBEAN, durum → WHEAT, chosen automatically from the preset). Its fill type copies that crop's weight, price and effects, and joins every fill category, fill sound and fill converter it's in. Without this, a new fill type can't go into a combine, trailer or silo, or be sold.
- **Cut swath:** crops that follow WHEAT, BARLEY, OAT, CANOLA or SOYBEAN can also be swathed like the base game's `*_CUT` fill types. That adds a `<FILLTYPE>_CUT` fill type with its own textures: a windrower cuts it, a grain pickup header threshes it back to grain, and a grass pickup header chops it to chaff.
- **Foliage XML additions:** FS25 sets windrows in the crop's own foliage XML, not in the fruit type list. The panel generates the lines to merge into `foliage/<crop>/<crop>.xml`, copied from the base crop it behaves like:
  - `<windrow fillType litersPerSqm cutFillType windrowCutFactor>`;
  - the fruit type categories, such as GRAINHEADER so headers can harvest it and PLANTER so planters can sow it;
  - the fruit type converters: MOWER to the windrow, COMBINE_MOWER to the swath, FORAGEHARVESTER to chaff;
  - `densityMapHeightType` entries so new fill types can lie on the ground. The output validates against the FS25 XML schema.
- **Saving:** crops and plant designs are saved in the browser. Use **Export Designs** and **Import Designs** to move them between browsers or share them.

The rendering code lives in `cropTextures.js`.
