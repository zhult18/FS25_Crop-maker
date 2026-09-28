# FS25_Crop-maker
A tool to create all the textures and XML needed for new Farming Simulator 25 crop types.

Open `index.html` in a browser. Nothing needs installing.

## Textures

The **Textures** tab draws a side-view foliage texture for each growth stage of a crop. The texture tiles left to right.

- **Plant Design:** pick a preset or build a crop from scratch. The settings cover plant form (stalk, bush, rosette or vine), height and stems, leaf shape, head or fruit type (spike, panicle, corn tassel and ear, sunflower disc, canola raceme, pods, cotton bolls, flowers, round fruit), when flowering and ripening happen, and colours for growing and ripe.
- **Presets:** the FS25 field crops, plus 49 US crops that aren't in the base game. See [docs/US_CROPS.md](docs/US_CROPS.md). A crop whose internal name matches a preset key (such as `DURUM` or `PEANUT`) uses that preset automatically.
- **Export:** DDS in BC3/DXT5, BC1/DXT1 or uncompressed RGBA, all with mipmaps, or PNG. There's an optional normal map. You can download one stage, or a ZIP of every stage.
- **Fill planes and windrows:** each crop gets top-down, tiling textures of its harvested material for trailers, heaps and silos. Materials are kernels, seeds, beans, tubers, roots, cotton, leaves or straw. For windrows, a crop either uses the base-game `STRAW` or its own straw texture. The own-straw option adds a `<FILLTYPE>_STRAW` fill type modelled on `STRAW`. Downloads include every map a fill type needs: diffuse, normal, height, displacement and distance. Height and displacement are single-channel (BC4, or 8-bit gray when uncompressed). Downloads also include a HUD icon, either a coloured heap or a flat white pictogram, and are laid out like your mod's folders. `maps_fillTypes.xml` points new crops and their straw at these files and their HUD icons. Paths use `.png`, and the game loads the `.dds` with the same name.
- **Saving:** crops and plant designs are saved in the browser. Use **Export Designs** and **Import Designs** to move them between browsers or share them.

The rendering code lives in `cropTextures.js`.
