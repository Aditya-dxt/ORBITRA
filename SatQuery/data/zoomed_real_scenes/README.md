# Zoomed Real Satellite Imagery Cache

This directory holds authentic bitemporal **ESA Sentinel-2 Level-2A** high-resolution surface reflectance imagery (optical RGB visual bands) acquired over targeted Indian infrastructure corridors via Microsoft Planetary Computer STAC.

## Hotspot Scenes Cached

1. **Kanpur / Bhauti PSIT Corridor (`kanpur_bhauti_nh19`)**:
   - Focus: National Highway 19 lane expansion and warehousing directly adjacent to PSIT Kanpur.
   - Files: `kanpur_bhauti_nh19_pre_real.png`, `kanpur_bhauti_nh19_post_real.png`, `kanpur_bhauti_nh19_meta.json`
2. **Kanpur / Panki Industrial Estate (`kanpur_panki_industrial`)**:
   - Focus: Factory sheds, rail logistics, and commercial ground modifications.
   - Files: `kanpur_panki_industrial_pre_real.png`, `kanpur_panki_industrial_post_real.png`, `kanpur_panki_industrial_meta.json`
3. **Delhi NCR / Gurugram Development Corridor (`delhi_gurugram_cybercity`)**:
   - Focus: Cyber City & Sector 29 high-density commercial developments along the expressway.
   - Files: `delhi_gurugram_cybercity_pre_real.png`, `delhi_gurugram_cybercity_post_real.png`, `delhi_gurugram_cybercity_meta.json`
4. **Bengaluru Electronic City (`bengaluru_electronic_city`)**:
   - Focus: Hosur Road Namma Metro Yellow Line viaduct and tech park developments.
   - Files: `bengaluru_electronic_city_pre_real.png`, `bengaluru_electronic_city_post_real.png`, `bengaluru_electronic_city_meta.json`
5. **Chennai Sriperumbudur (`chennai_sriperumbudur`)**:
   - Focus: Automotive manufacturing and industrial building footprint expansion.
   - Files: `chennai_sriperumbudur_pre_real.png`, `chennai_sriperumbudur_post_real.png`, `chennai_sriperumbudur_meta.json`

## Processing & Verification

Run the verification script to regenerate all visual inspection maps, heatmaps, and close-up chips:
```bash
python SatQuery/examples/download_zoomed_real_scenes.py
```
Outputs are written to: `SatQuery/exports/zoomed_change_verification/`
