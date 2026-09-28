# US crops not in the FS25 base game

A survey of field crops grown commercially in the US that FS25 doesn't ship, including close variants of base-game crops. Each one has a plant-design preset in `cropTextures.js`. Add a crop whose internal name matches the preset key (for example `DURUM`), and the Textures tab uses that look automatically. Any crop can also pick a preset from **Start From Preset**.

Acreage figures are approximate. Figures marked **(S)** come from USDA NASS / ERS numbers found in search results. The rest are rough estimates from NASS and Census data for 2022–25, good to about ±30%. Check them in [NASS Quick Stats](https://quickstats.nass.usda.gov/) before relying on them.

## Add first

These are ranked by acreage and by interest for a US map.

1. **Wheat classes:** `HRWWHEAT` (~23M acres), `HRSWHEAT` (9.4M **(S)**), `SRWWHEAT`, `WHITEWHEAT`. Each is a recolour of wheat with different awns.
2. `DURUM`: 2.0M acres **(S)**, in ND and MT. Long black awns and a bluish, waxy leaf.
3. `ALFALFA`: about 15M acres harvested for hay. Cut green several times a year.
4. `PEANUT`: 1.9M acres **(S)**, in GA, AL and TX. A low vine; the nuts grow underground.
5. **Dry beans:** `PINTOBEAN`, `BLACKBEAN`, `NAVYBEAN`, `KIDNEYBEAN`. Pod bushes that dry down before harvest.
6. `RYE`: tall, with long awns.
7. `DRYPEA` and `LENTIL`: Northern Plains pulses.
8. `CHICKPEA`: 0.54M acres **(S)**.
9. `SWEETCORN` (harvested green) and `POPCORN`.
10. `PIMACOTTON`: 171k acres **(S)**. Taller than upland cotton.
11. `TOBACCO`: 185–200k acres **(S)**, in NC and KY.
12. `ONION`: tubular leaves that fall over and brown before harvest.
13. `SWEETPOTATO`: a vine with heart-shaped leaves.
14. **Northern Plains oilseeds:** `FLAX`, `CAMELINA`, `MUSTARD`.
15. **Niche crops:** `HEMP` (45k acres **(S)**) and `PROSOMILLET`. Hops is covered below.

## All presets by plant form

| Form | Presets |
|---|---|
| Grain (stalk + head) | HRWWHEAT, SRWWHEAT, WHITEWHEAT, HRSWHEAT, DURUM, SPELT, RYE, TRITICALE, REDOAT, PROSOMILLET, WILDRICE, TEFF, TIMOTHY, SWITCHGRASS |
| Tall stalk | SWEETCORN, POPCORN, SORGHUMSUDAN, BROOMCORN, PEARLMILLET, HEMP, TOBACCO |
| Disc / flower heads | CONFECTIONSUNFLOWER, SAFFLOWER, FLAX, BUCKWHEAT, PEPPERMINT |
| Raceme + pods | CAMELINA, MUSTARD |
| Bush with pods or bolls | PINTOBEAN, NAVYBEAN, BLACKBEAN, KIDNEYBEAN, COWPEA, CHICKPEA, LENTIL, PIMACOTTON, CHILEPEPPER, TOMATO, ALFALFA, CLOVER |
| Rosette | ONION, GARLIC, LETTUCE, CABBAGE |
| Vine | PEANUT, SWEETPOTATO, PUMPKIN, WATERMELON, DRYPEA |

## Typical US seasons

These are the main-region planting and harvest months. They're useful when you fill in the Calendar tab.

| Crop | Plant | Harvest |
|---|---|---|
| Hard red winter / soft red winter / white winter wheat, rye, triticale, spelt | Sep–Oct | Jun–Jul |
| Hard red spring wheat, durum | Apr–May | Aug |
| Proso millet | Jun | Sep |
| Sweet corn | Apr–Jun | Jul–Sep |
| Popcorn | May | Sep–Oct |
| Hemp | May–Jun | Aug–Oct |
| Confection sunflower | May–Jun | Oct |
| Safflower | Mar–May | Aug–Sep |
| Flax, camelina, mustard | Apr–May | Jul–Aug |
| Buckwheat | Jun–Jul | Sep–Oct |
| Tobacco | Apr–May (transplant) | Jul–Sep |
| Dry beans | May–Jun | Sep |
| Chickpea, lentil, dry pea | Apr–May | Jul–Aug |
| Alfalfa | Apr–Aug (perennial) | May–Oct, 3–10 cuts |
| Onion | Feb–Apr | Jul–Sep |
| Peanut | Apr–May | Sep–Oct |
| Sweet potato | May–Jun | Sep–Oct |
| Pumpkin | May–Jun | Sep–Oct |
| Pima cotton | Apr | Oct–Nov |

## Not covered

- **Hops** (41.7k acres **(S)**, mostly in WA) grows on 18 ft trellises, which doesn't fit a field foliage billboard.
- **Cranberries** grow in flooded bogs.
- **Orchard, tree and greenhouse crops** were out of scope.

## Sources

- [NASS Acreage, June 2025 briefing](https://data.nass.usda.gov/Newsroom/Executive_Briefings/2025/06-30-2025.pdf)
- [NASS Acreage, 06/30/2025](https://release.nass.usda.gov/reports/acrg0625.pdf)
- [NASS Prospective Plantings 2025](https://www.nass.usda.gov/Publications/Todays_Reports/reports/pspl0325.pdf)
- [NASS National Hemp Report 2024 briefing](https://data.nass.usda.gov/Newsroom/Executive_Briefings/2025/04-17-2025.pdf)
- [ERS Vegetables and Pulses Outlook VGS-376](https://ers.usda.gov/sites/default/files/_laserfiche/outlooks/113070/VGS-376.pdf)
- [Cotton Grower: 2025 planted acres, Pima 171k](https://www.cottongrower.com/cotton-production/production-outlook-acreage/usda-report-pegs-10-1-million-total-planted-cotton-acres-for-2025/)
- [TAMU AFPC: peanut acres at a 34-year high](https://sat-wp.afpc.tamu.edu/2025/07/23/planted-peanut-acres-at-thirty-four-year-high)
- [Capital Press: 2025 US hops](https://capitalpress.com/2025/12/30/u-s-hops-production-acreage-continue-drop-in-2025-but-yield-price-and-value-improve/)
- [NC State: 2025 flue-cured tobacco outlook](https://content.ces.ncsu.edu/pdf/us-tobacco-situation-and-outlook/2025-01-08/1.__and_Outlook_CGldyAU.pdf)
- [US Dry Bean Council production facts](https://usdrybeans.com/industry/production-facts/)
