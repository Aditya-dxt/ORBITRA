# SatQuery Native GIS Integration & Layer Ingestion Guide

**Module:** SatQuery (Computer Vision & Spatial Analytics)  
**Project:** ORBITRA  
**Standard Compliance:** OGC GeoTIFF 1.1 | RFC 7946 GeoJSON | EPSG:4326 (WGS-84)  
**Status:** Production Ready  

---

## 1. Overview of GIS Deliverables

SatQuery generates standards-compliant geospatial raster and vector data packages for each operational satellite change verification corridor. All generated layers are immediately compatible with leading Geographic Information Systems, including **QGIS Desktop**, **ESRI ArcGIS Pro**, and **Google Earth Engine (GEE)**.

For each geographic mission corridor, the following layers are exported to `SatQuery/exports/gis/<zone_key>/`:

| Artifact | File Format | Type | Description |
| :--- | :--- | :--- | :--- |
| **Pre-Change Scene** | `.tif` (GeoTIFF) | Raster (RGB 3-band) | Calibrated surface reflectance Sentinel-2 L2A optical imagery at epoch $T_1$. |
| **Post-Change Scene** | `.tif` (GeoTIFF) | Raster (RGB 3-band) | Calibrated surface reflectance Sentinel-2 L2A optical imagery at epoch $T_2$. |
| **Change Probability Heatmap** | `.tif` (GeoTIFF) | Raster (1-band float/uint8) | Continuous pixel-level change confidence $\in [0, 255]$ ($0.0 \to 1.0$). |
| **Binary Change Mask** | `.tif` (GeoTIFF) | Raster (1-band uint8) | Thresholded binary detection mask ($0 = \text{unchanged}, 255 = \text{changed}$). |
| **Candidate Vector Polygons** | `.geojson` | Vector (RFC 7946) | Closed geodetic bounding boxes with complete candidate provenance attributes. |
| **Corridor GIS Manifest** | `.json` | Metadata | Affine transformation matrix, spatial extents, GSD, and layer registry. |

---

## 2. Georeferencing Framework & Affine Transformation

Each GeoTIFF contains embedded OGC TIFF directory tags linking raster pixel coordinates $(u, v)$ to the WGS-84 geographic coordinate reference system (EPSG:4326):

1. **ModelPixelScaleTag (Tag 33550):**  
   $$\text{ScaleX} = \frac{\text{GSD}_x}{\text{MetersPerDegreeLon}}, \quad \text{ScaleY} = \frac{\text{GSD}_y}{\text{MetersPerDegreeLat}}, \quad \text{ScaleZ} = 0.0$$
2. **ModelTiepointTag (Tag 33922):**  
   Maps raster pixel $(0, 0, 0)$ directly to top-left geodetic coordinates:  
   $$(I, J, K, X, Y, Z) = (0.0, 0.0, 0.0, \text{Lon}_0, \text{Lat}_0, 0.0)$$
3. **GeoKeyDirectoryTag (Tag 34735):**  
   Specifies standard OGC keys: `GTModelTypeGeoKey = 2` (ModelTypeGeographic), `GTRasterTypeGeoKey = 1` (RasterPixelIsArea), and `GeographicTypeGeoKey = 4326` (WGS-84).

### Affine Coordinate Mapping Equation:
$$\begin{bmatrix} \text{Lon} \\ \text{Lat} \end{bmatrix} = \begin{bmatrix} \text{ScaleX} & 0 \\ 0 & \text{ScaleY} \end{bmatrix} \begin{bmatrix} u \\ v \end{bmatrix} + \begin{bmatrix} \text{Lon}_0 \\ \text{Lat}_0 \end{bmatrix}$$

---

## 3. Directory Layout

```text
SatQuery/exports/gis/
├── kanpur_bhauti/
│   ├── kanpur_bhauti_pre_t1.tif
│   ├── kanpur_bhauti_post_t2.tif
│   ├── kanpur_bhauti_change_heatmap.tif
│   ├── kanpur_bhauti_binary_mask.tif
│   ├── kanpur_bhauti_candidates.geojson
│   └── kanpur_bhauti_gis_manifest.json
├── delhi_ncr/
│   └── ... (same layout)
├── bengaluru_tech/
│   └── ... (same layout)
└── chennai_sriperumbudur/
    └── ... (same layout)
```

---

## 4. QGIS Desktop Ingestion & Symbology Setup

Follow these steps to visualize and inspect SatQuery layers in QGIS:

### Step 1: Add Raster Basemaps and Imagery
1. Launch **QGIS** (v3.22+ recommended).
2. Set Project CRS to `EPSG:4326 - WGS 84` (bottom right corner).
3. Drag and drop `<zone>_pre_t1.tif` and `<zone>_post_t2.tif` into the Layers panel.
4. *Optional:* Toggle layer visibility or use the **Map Swipe Tool** plugin to visually compare $T_1$ vs $T_2$.

### Step 2: Render Change Probability Heatmap
1. Drag and drop `<zone>_change_heatmap.tif` into the Layers panel.
2. Right-click the layer $\to$ **Properties** $\to$ **Symbology**.
3. Set **Render type** to **Singleband pseudocolor**.
4. Set **Color ramp** to **Magma** or **Turbo** (Min: `0`, Max: `255`).
5. Under **Layer Rendering**, set **Opacity** to `75%` and blending mode to `Multiply`.

### Step 3: Add Candidate Vector Polygons
1. Drag and drop `<zone>_candidates.geojson` onto the map canvas.
2. Right-click the layer $\to$ **Properties** $\to$ **Symbology**:
   - Set **Fill** to `No Brush` (transparent interior).
   - Set **Stroke Color** to `#FF3C00` (Safety Orange) with **Stroke Width** = `0.8 mm`.
3. Switch to the **Labels** tab:
   - Select **Single Labels** using value: `concat(candidate_id, '\n(p=', round(confidence, 2), ', u=', round(uncertainty, 2), ')')`.
   - Set text font to bold, size `8 pt`, with a white buffer outline (`1.0 mm`).

---

## 5. ESRI ArcGIS Pro Ingestion Walkthrough

1. Open **ArcGIS Pro** and create or open a Map view.
2. In the **Catalog** pane, navigate to `SatQuery/exports/gis/<zone_key>/`.
3. Right-click `<zone>_post_t2.tif` $\to$ **Add To Current Map**.
4. Drag `<zone>_change_heatmap.tif` into the map:
   - In the **Appearance** ribbon tab, set Symbology to **Classified** or **Stretch** with the `Heat Map` color ramp.
5. Drag `<zone>_candidates.geojson` into the map:
   - Style polygons with hollow fill and bright yellow/red stroke.
   - Open Attribute Table to inspect `local_grid_x_m`, `local_grid_y_m`, `transit_distance_m`, `confidence`, and `uncertainty`.

---

## 6. Google Earth Engine (GEE) Ingestion Script

To load and analyze SatQuery GeoJSON candidate polygons in Google Earth Engine Python API:

```python
import ee
import json

ee.Initialize()

# Load candidate vector polygons from local GeoJSON
with open("SatQuery/exports/gis/kanpur_bhauti/kanpur_bhauti_candidates.geojson") as f:
    geojson_data = json.load(f)

# Convert to Earth Engine FeatureCollection
ee_candidates = ee.FeatureCollection(geojson_data["features"])

# Define inspection buffer around candidate centroids
def add_buffer(feature):
    return feature.buffer(50)  # 50-meter inspection circle

buffered_targets = ee_candidates.map(add_buffer)
print(f"Loaded {ee_candidates.size().getInfo()} verification targets into GEE.")
```

---

## 7. Programmatic Generation CLI

To re-export or update all GIS packages across all 4 corridors:

```bash
# Export all 4 corridors
python SatQuery/examples/export_gis_layers.py --zone all

# Export single corridor (e.g. Kanpur)
python SatQuery/examples/export_gis_layers.py --zone kanpur_bhauti
```
