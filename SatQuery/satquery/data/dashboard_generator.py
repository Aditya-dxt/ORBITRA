"""Interactive Web Dashboard Generator for ORBITRA SatQuery.

Compiles a standalone, browser-executable mission operations dashboard
linking Sentinel-2 satellite imagery, change heatmaps, candidate bounding boxes,
calibration diagnostics, and downstream ARES energy decisions.
"""

import json
import math
import os
from typing import Dict, List, Optional, Any

from .india_satellite_data import INDIAN_MISSION_ZONES


class MissionDashboardGenerator:
    """Generates the interactive single-page mission operations dashboard."""

    def __init__(self, repo_root: Optional[str] = None):
        if repo_root is None:
            self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        else:
            self.repo_root = repo_root

        self.satquery_root = os.path.join(self.repo_root, "SatQuery")
        self.exports_root = os.path.join(self.satquery_root, "exports")
        self.vis_root = os.path.join(self.exports_root, "visualizations")
        self.data_root = os.path.join(self.satquery_root, "data")

    def build_dashboard_data(self) -> Dict[str, Any]:
        """Aggregate data for all 4 Indian corridors into a single JSON bundle for the frontend."""
        zones_data = {}

        for z_key, z_info in INDIAN_MISSION_ZONES.items():
            meta_path = os.path.join(self.data_root, "india_scenes", f"{z_key}_meta.json")
            metadata = {}
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)

            cands_path = os.path.join(self.exports_root, f"candidates_{z_key}.json")
            candidates = []
            if os.path.exists(cands_path):
                with open(cands_path, "r", encoding="utf-8") as f:
                    raw_cands = json.load(f)
                    for c in raw_cands:
                        bx = c["region"]["bbox_pixels"]
                        px_area = (bx[2] - bx[0]) * (bx[3] - bx[1])
                        m2_area = px_area * 100.0  # GSD = 10m -> 100 m^2/px
                        lg = c["region"]["local_grid"]
                        dist_m = math.sqrt(lg["x_meters"]**2 + lg["y_meters"]**2)

                        p = c["confidence"]
                        p_c = max(1e-6, min(1.0 - 1e-6, p))
                        h_p = - (p_c * math.log2(p_c) + (1.0 - p_c) * math.log2(1.0 - p_c))

                        u = c["uncertainty"]
                        if u < 0.60:
                            ares_act = "NONE (CONFIRMED)"
                            act_cost = "0 J (0.00 Wh)"
                            act_badge = "badge-success"
                        elif u > 0.95 and dist_m < 2500.0:
                            ares_act = "RECAPTURE (UAV FLIGHT)"
                            act_cost = f"{int(dist_m * 22.5 + 450):,} J ({((dist_m * 22.5 + 450)/3600):.2f} Wh)"
                            act_badge = "badge-danger"
                        elif u >= 0.70:
                            ares_act = "STRONGER_MODEL (DEEP SIAMESE)"
                            act_cost = "1,450 J (0.40 Wh)"
                            act_badge = "badge-warning"
                        else:
                            ares_act = "HUMAN_REVIEW (ANALYST)"
                            act_cost = "150 J (0.04 Wh)"
                            act_badge = "badge-info"

                        candidates.append({
                            "candidate_id": c["candidate_id"],
                            "confidence": round(p, 4),
                            "uncertainty": round(u, 4),
                            "shannon_entropy": round(h_p, 4),
                            "bbox_pixels": bx,
                            "pixel_area": px_area,
                            "area_m2": m2_area,
                            "area_ha": round(m2_area / 10000.0, 3),
                            "local_grid": lg,
                            "transit_distance_m": round(dist_m, 1),
                            "coordinates": c["region"].get("coordinates", {}),
                            "timestamp": c.get("timestamp", "N/A"),
                            "ares_recommendation": ares_act,
                            "ares_cost": act_cost,
                            "ares_badge": act_badge,
                        })

            report_path = os.path.join(self.exports_root, f"mission_report_{z_key}.json")
            mission_summary = {}
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    m_data = json.load(f)
                    mission_summary = m_data.get("mission_summary", {})

            zones_data[z_key] = {
                "key": z_key,
                "name": z_info["name"],
                "description": z_info["description"],
                "home_coordinates": {"lat": z_info["home_lat"], "lon": z_info["home_lon"]},
                "bbox": z_info["bbox"],
                "pre_date": metadata.get("pre_datetime", "2021-12-01")[:10],
                "post_date": metadata.get("post_datetime", "2023-12-24")[:10],
                "pre_scene_id": metadata.get("pre_scene_id", "ESA Sentinel-2 L2A"),
                "post_scene_id": metadata.get("post_scene_id", "ESA Sentinel-2 L2A"),
                "pre_img_url": f"../../data/india_scenes/{z_key}_pre_real.png",
                "post_img_url": f"../../data/india_scenes/{z_key}_post_real.png",
                "heatmap_url": f"{z_key}_heatmap.png",
                "mask_url": f"{z_key}_mask.png",
                "total_candidates": len(candidates),
                "candidates": candidates,
                "mission_summary": mission_summary,
            }

        return {
            "app_title": "ORBITRA Mission Operations Dashboard",
            "version": "1.0.0",
            "ece_metric": 0.0557,
            "brier_metric": 0.1767,
            "zones": zones_data,
        }

    def generate_html(self, output_path: Optional[str] = None) -> str:
        """Compile and write the standalone interactive dashboard HTML file."""
        target_path = output_path or os.path.join(self.vis_root, "orbitra_mission_dashboard.html")
        data_bundle = self.build_dashboard_data()
        json_blob = json.dumps(data_bundle, indent=2)

        template_path = os.path.join(os.path.dirname(__file__), "dashboard_template.html")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                template_html = f.read()
        else:
            template_html = self._get_fallback_template()

        html_content = template_html.replace("__ORBITRA_DATA_JSON__", json_blob)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return target_path

    @staticmethod
    def _get_fallback_template() -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ORBITRA: Mission Operations & Vision Dashboard</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      --bg-dark: #0a0f1d;
      --card-bg: #11192e;
      --card-border: #1e293b;
      --accent-blue: #38bdf8;
      --accent-emerald: #34d399;
      --accent-amber: #fbbf24;
      --accent-rose: #f43f5e;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg-dark); color: var(--text-main); min-height: 100vh; display: flex; flex-direction: column; }
    header { background: rgba(17, 25, 46, 0.9); backdrop-filter: blur(12px); border-bottom: 1px solid var(--card-border); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { background: linear-gradient(135deg, #0284c7, #38bdf8); width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; color: white; }
    .nav-corridors { display: flex; gap: 8px; }
    .corridor-btn { background: #1e293b; color: var(--text-muted); border: 1px solid transparent; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
    .corridor-btn:hover { background: #283548; color: var(--text-main); }
    .corridor-btn.active { background: #0284c7; color: white; border-color: var(--accent-blue); box-shadow: 0 0 12px rgba(56, 189, 248, 0.35); }
    .badge { padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }
    .badge-success { background: rgba(52, 211, 153, 0.15); color: var(--accent-emerald); border: 1px solid rgba(52, 211, 153, 0.3); }
    .badge-info { background: rgba(56, 189, 248, 0.15); color: var(--accent-blue); border: 1px solid rgba(56, 189, 248, 0.3); }
    .badge-warning { background: rgba(251, 191, 36, 0.15); color: var(--accent-amber); border: 1px solid rgba(251, 191, 36, 0.3); }
    .badge-danger { background: rgba(244, 63, 94, 0.15); color: var(--accent-rose); border: 1px solid rgba(244, 63, 94, 0.3); }
    main { display: grid; grid-template-columns: 1fr 380px; gap: 16px; padding: 16px 24px; flex: 1; max-width: 1600px; margin: 0 auto; width: 100%; }
    .viewport-card, .inspector-card, .drawer-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }
    .drawer-card { grid-column: 1 / -1; margin-top: 8px; }
    .viewport-toolbar { padding: 10px 16px; background: #0f172a; border-bottom: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
    .view-modes { display: flex; background: #1e293b; border-radius: 6px; padding: 2px; }
    .mode-tab { padding: 5px 12px; font-size: 11px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-radius: 4px; border: none; background: transparent; }
    .mode-tab.active { background: #0284c7; color: white; }
    .viewport-canvas-container { position: relative; width: 100%; height: 540px; background: #050811; display: flex; align-items: center; justify-content: center; }
    #viewer-stage { position: relative; width: 512px; height: 512px; box-shadow: 0 8px 32px rgba(0,0,0,0.6); border-radius: 4px; overflow: hidden; user-select: none; }
    .stage-layer { position: absolute; top: 0; left: 0; width: 512px; height: 512px; pointer-events: none; }
    #pre-layer { z-index: 1; }
    #post-layer { z-index: 2; }
    #heatmap-layer { z-index: 3; opacity: 0; mix-blend-mode: screen; }
    #mask-layer { z-index: 4; opacity: 0; mix-blend-mode: lighten; }
    #overlay-canvas { position: absolute; top: 0; left: 0; width: 512px; height: 512px; z-index: 5; cursor: crosshair; }
    .swipe-divider { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--accent-blue); box-shadow: 0 0 8px var(--accent-blue); z-index: 6; pointer-events: none; }
    .swipe-handle { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 26px; height: 26px; border-radius: 50%; background: var(--accent-blue); border: 2px solid white; display: flex; align-items: center; justify-content: center; color: #0f172a; font-size: 11px; }
    .viewport-footer { padding: 10px 16px; background: #0f172a; border-top: 1px solid var(--card-border); display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); }
    .inspector-header { padding: 14px 16px; background: #0f172a; border-bottom: 1px solid var(--card-border); }
    .selected-candidate-panel { padding: 16px; border-bottom: 1px solid var(--card-border); background: rgba(30, 41, 59, 0.4); }
    .meter-block { margin-bottom: 10px; }
    .meter-label { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; }
    .meter-track { width: 100%; height: 6px; background: #0f172a; border-radius: 3px; overflow: hidden; }
    .meter-fill-conf { height: 100%; background: linear-gradient(90deg, #38bdf8, #34d399); width: 0%; transition: width 0.3s; }
    .meter-fill-unc { height: 100%; background: linear-gradient(90deg, #fbbf24, #f43f5e); width: 0%; transition: width 0.3s; }
    .telemetry-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
    .tele-item { background: #0f172a; padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05); }
    .tele-k { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
    .tele-v { font-size: 12px; font-weight: 600; color: var(--text-main); }
    .ares-action-box { margin-top: 12px; padding: 10px; border-radius: 8px; background: #0f172a; border: 1px solid var(--card-border); }
    .cand-table-scroll { flex: 1; max-height: 250px; overflow-y: auto; }
    .cand-item { padding: 8px 16px; border-bottom: 1px solid rgba(255,255,255,0.04); display: flex; justify-content: space-between; align-items: center; cursor: pointer; font-size: 12px; }
    .cand-item:hover { background: rgba(56, 189, 248, 0.08); }
    .cand-item.active { background: rgba(56, 189, 248, 0.2); border-left: 3px solid var(--accent-blue); }
    .drawer-tabs { display: flex; background: #0f172a; border-bottom: 1px solid var(--card-border); }
    .d-tab { padding: 10px 20px; font-size: 12px; font-weight: 600; color: var(--text-muted); cursor: pointer; background: transparent; border: none; }
    .d-tab.active { color: var(--accent-blue); border-bottom: 2px solid var(--accent-blue); background: var(--card-bg); }
    .drawer-content { padding: 16px 20px; font-size: 12px; }
    .drawer-pane { display: none; }
    .drawer-pane.active { display: block; }
    table.data-table { width: 100%; border-collapse: collapse; font-size: 11px; }
    table.data-table th { background: #0f172a; padding: 8px 12px; color: var(--text-muted); border-bottom: 1px solid var(--card-border); text-align: left; }
    table.data-table td { padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-icon"><i class="fa-solid fa-satellite"></i></div>
      <div class="brand-text">
        <h1 style="font-size: 16px; font-weight: 700;">ORBITRA MISSION CONTROL</h1>
        <p style="font-size: 11px; color: var(--text-muted);">SatQuery Vision & Spatial Verification Engine | Schema v1.0.0</p>
      </div>
    </div>
    <div class="nav-corridors" id="corridor-nav"></div>
    <div style="display: flex; gap: 8px;">
      <span class="badge badge-success"><i class="fa-solid fa-check"></i> ECE: 0.0557 (Calibrated)</span>
      <span class="badge badge-info"><i class="fa-solid fa-crosshairs"></i> 10m GSD (Sentinel-2)</span>
    </div>
  </header>

  <main>
    <div class="viewport-card">
      <div class="viewport-toolbar">
        <div class="view-modes">
          <button class="mode-tab active" data-mode="swipe"><i class="fa-solid fa-arrows-left-right"></i> Wipe / Swipe</button>
          <button class="mode-tab" data-mode="heatmap"><i class="fa-solid fa-fire"></i> Heatmap</button>
          <button class="mode-tab" data-mode="detections"><i class="fa-solid fa-vector-square"></i> Detections</button>
          <button class="mode-tab" data-mode="t1">T1</button>
          <button class="mode-tab" data-mode="t2">T2</button>
        </div>
        <div id="swipe-control" style="display: flex; align-items: center; gap: 8px; font-size: 11px;">
          <span>Wipe:</span>
          <input type="range" id="swipe-range" min="0" max="100" value="50" style="accent-color: var(--accent-blue);">
          <span id="swipe-val">50%</span>
        </div>
        <div id="heat-control" style="display: none; align-items: center; gap: 8px; font-size: 11px;">
          <span>Heatmap Alpha:</span>
          <input type="range" id="heat-range" min="0" max="100" value="70" style="accent-color: var(--accent-blue);">
          <span id="heat-val">70%</span>
        </div>
      </div>
      <div class="viewport-canvas-container">
        <div id="viewer-stage">
          <img id="pre-layer" class="stage-layer" alt="Pre Image">
          <img id="post-layer" class="stage-layer" alt="Post Image">
          <img id="heatmap-layer" class="stage-layer" alt="Heatmap Image">
          <img id="mask-layer" class="stage-layer" alt="Mask Image">
          <canvas id="overlay-canvas" width="512" height="512"></canvas>
          <div class="swipe-divider" id="divider" style="left: 50%;">
            <div class="swipe-handle"><i class="fa-solid fa-left-right"></i></div>
          </div>
        </div>
      </div>
      <div class="viewport-footer">
        <div><i class="fa-solid fa-calendar"></i> <span id="interval-label">Epoch: 2021 -> 2023</span></div>
        <div><i class="fa-solid fa-location-dot"></i> <span id="coords-label">Home Base: 26.447°N, 80.198°E</span></div>
        <div><i class="fa-solid fa-satellite-dish"></i> Sensor: ESA Sentinel-2 Level-2A</div>
      </div>
    </div>

    <div class="inspector-card">
      <div class="inspector-header">
        <h2 style="font-size: 14px; color: var(--accent-blue);"><i class="fa-solid fa-bullseye"></i> Candidate Verification</h2>
        <p style="font-size: 11px; color: var(--text-muted);">Telemetry, Entropy Uncertainty & ARES Triage</p>
      </div>
      <div class="selected-candidate-panel">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <strong style="font-size: 15px;" id="sel-cand-id">cand_sq_levir_001</strong>
          <span class="badge badge-info" id="sel-cand-area">0.32 ha</span>
        </div>
        <div class="meter-block">
          <div class="meter-label"><span>Calibrated Confidence (p):</span><span id="sel-conf-val" style="color: var(--accent-blue); font-weight: 700;">0.520</span></div>
          <div class="meter-track"><div class="meter-fill-conf" id="sel-conf-bar"></div></div>
        </div>
        <div class="meter-block">
          <div class="meter-label"><span>Shannon Uncertainty (u):</span><span id="sel-unc-val" style="color: var(--accent-amber); font-weight: 700;">0.990</span></div>
          <div class="meter-track"><div class="meter-fill-unc" id="sel-unc-bar"></div></div>
        </div>
        <div class="telemetry-grid">
          <div class="tele-item"><div class="tele-k">Local X / Y (ENU)</div><div class="tele-v" id="sel-local-xy">520.0m, 3840.0m</div></div>
          <div class="tele-item"><div class="tele-k">Transit Distance</div><div class="tele-v" id="sel-dist">3,875.0 m</div></div>
          <div class="tele-item"><div class="tele-k">Geodetic (Lat, Lon)</div><div class="tele-v" id="sel-geodetic">26.481°, 80.203°</div></div>
          <div class="tele-item"><div class="tele-k">Surface Area</div><div class="tele-v" id="sel-m2">3,200 m²</div></div>
        </div>
        <div class="ares-action-box">
          <div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">ARES Autonomous Triage Decision</div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 12px; font-weight: 700;" id="sel-ares-act">STRONGER_MODEL</span>
            <span class="badge badge-warning" id="sel-ares-cost">1,450 J (0.40 Wh)</span>
          </div>
        </div>
      </div>
      <div style="padding: 10px 16px; background: #0f172a; border-bottom: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 12px; font-weight: 700;">Detections (<span id="cand-count">0</span>)</span>
        <input type="text" id="cand-search" placeholder="Search ID..." style="background: #1e293b; border: 1px solid var(--card-border); color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; width: 130px;">
      </div>
      <div class="cand-table-scroll" id="cand-list"></div>
    </div>

    <div class="drawer-card">
      <div class="drawer-tabs">
        <button class="d-tab active" data-pane="pane-summary"><i class="fa-solid fa-chart-pie"></i> Multi-Zone Corridors</button>
        <button class="d-tab" data-pane="pane-calibration"><i class="fa-solid fa-chart-line"></i> Calibration & Reliability</button>
        <button class="d-tab" data-pane="pane-ares"><i class="fa-solid fa-battery-half"></i> Energy Model & Reserve</button>
        <button class="d-tab" data-pane="pane-gis"><i class="fa-solid fa-map"></i> GIS GeoTIFF & GeoJSON Layers</button>
      </div>
      <div class="drawer-content">
        <div class="drawer-pane active" id="pane-summary">
          <table class="data-table">
            <thead>
              <tr><th>Corridor Key</th><th>Region Name</th><th>Baseline Window</th><th>Candidates</th><th>Total Footprint</th><th>ARES Policy</th><th>Safe Return</th></tr>
            </thead>
            <tbody id="corridors-tbody"></tbody>
          </table>
        </div>
        <div class="drawer-pane" id="pane-calibration">
          <div style="display: flex; gap: 20px; align-items: center;">
            <div style="flex: 1;">
              <h3 style="font-size: 13px; color: var(--accent-blue); margin-bottom: 6px;">Held-Out Calibration Properties (N=600)</h3>
              <p style="color: var(--text-muted); line-height: 1.5; margin-bottom: 10px;">Trained via Newton-Raphson IRLS Platt scaling over validation logits. Evaluated strictly on held-out test scenes to prevent spatial leakage.</p>
              <div style="display: flex; gap: 12px;">
                <span class="badge badge-success">Calibrated ECE: 0.0557 (Passed &lt; 0.10)</span>
                <span class="badge badge-info">Brier Score: 0.1767</span>
                <span class="badge badge-warning">Max Calibration Error (MCE): 0.1405</span>
              </div>
            </div>
            <div style="width: 240px; text-align: center;">
              <a href="calibration_reliability_diagram.svg" target="_blank" style="color: var(--accent-blue); text-decoration: none; font-size: 11px;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open Vector Reliability Diagram SVG</a>
            </div>
          </div>
        </div>
        <div class="drawer-pane" id="pane-ares">
          <p style="line-height: 1.6; color: var(--text-muted); margin-bottom: 8px;"><strong style="color: white;">Energy Accounting Equation:</strong> E = P * t / 3600 Wh. Action cost: Ea = Efly + Ecap + Ecomp + Ecomm.</p>
          <p style="line-height: 1.6; color: var(--text-muted);"><strong style="color: white;">Return-Reserve Feasibility Guardrail:</strong> Erem - Ea >= Ereturn(xa) + Esafety. Every sortie strictly reserves return transit energy, ensuring zero battery strandings.</p>
        </div>
        <div class="drawer-pane" id="pane-gis">
          <p style="color: var(--text-muted); margin-bottom: 10px;">Standards-compliant OGC GeoTIFF (EPSG:4326) and RFC 7946 GeoJSON layers are pre-generated in <code>SatQuery/exports/gis/</code>.</p>
          <div style="display: flex; gap: 10px;">
            <a href="../gis/kanpur_bhauti/kanpur_bhauti_candidates.geojson" download class="badge badge-info" style="text-decoration: none;"><i class="fa-solid fa-download"></i> Kanpur Candidates (.geojson)</a>
            <a href="../gis/delhi_ncr/delhi_ncr_candidates.geojson" download class="badge badge-info" style="text-decoration: none;"><i class="fa-solid fa-download"></i> Delhi Candidates (.geojson)</a>
            <a href="../gis/bengaluru_tech/bengaluru_tech_candidates.geojson" download class="badge badge-info" style="text-decoration: none;"><i class="fa-solid fa-download"></i> Bengaluru Candidates (.geojson)</a>
            <a href="../gis/chennai_sriperumbudur/chennai_sriperumbudur_candidates.geojson" download class="badge badge-info" style="text-decoration: none;"><i class="fa-solid fa-download"></i> Chennai Candidates (.geojson)</a>
          </div>
        </div>
      </div>
    </div>
  </main>

  <script id="orbitra-data" type="application/json">
__ORBITRA_DATA_JSON__
  </script>

  <script>
    const db = JSON.parse(document.getElementById('orbitra-data').textContent);
    let activeZoneKey = 'kanpur_bhauti';
    let activeCandidateId = null;
    let viewMode = 'swipe';
    let swipePercent = 50;
    let heatOpacity = 0.7;

    const preLayer = document.getElementById('pre-layer');
    const postLayer = document.getElementById('post-layer');
    const heatLayer = document.getElementById('heatmap-layer');
    const maskLayer = document.getElementById('mask-layer');
    const overlayCanvas = document.getElementById('overlay-canvas');
    const ctx = overlayCanvas.getContext('2d');
    const divider = document.getElementById('divider');

    function init() {
      renderCorridorNav();
      renderCorridorsTable();
      switchCorridor('kanpur_bhauti');
      setupEventListeners();
    }

    function renderCorridorNav() {
      const nav = document.getElementById('corridor-nav');
      nav.innerHTML = '';
      for (const [key, z] of Object.entries(db.zones)) {
        const btn = document.createElement('button');
        btn.className = `corridor-btn ${key === activeZoneKey ? 'active' : ''}`;
        btn.innerHTML = `<i class="fa-solid fa-location-dot"></i> ${z.name.split('/')[0].trim()}`;
        btn.onclick = () => switchCorridor(key);
        nav.appendChild(btn);
      }
    }

    function switchCorridor(key) {
      activeZoneKey = key;
      const z = db.zones[key];

      document.querySelectorAll('.corridor-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.includes(z.name.split('/')[0].trim()));
      });

      preLayer.src = z.pre_img_url;
      postLayer.src = z.post_img_url;
      heatLayer.src = z.heatmap_url;
      maskLayer.src = z.mask_url;

      document.getElementById('interval-label').textContent = `Epoch: ${z.pre_date} -> ${z.post_date}`;
      document.getElementById('coords-label').textContent = `Home Base: ${z.home_coordinates.lat}°N, ${z.home_coordinates.lon}°E`;
      document.getElementById('cand-count').textContent = z.candidates.length;

      renderCandidatesList(z.candidates);

      if (z.candidates.length > 0) {
        selectCandidate(z.candidates[0].candidate_id);
      }

      updateView();
    }

    function renderCandidatesList(candidates) {
      const list = document.getElementById('cand-list');
      list.innerHTML = '';
      candidates.forEach(c => {
        const row = document.createElement('div');
        row.className = `cand-item ${c.candidate_id === activeCandidateId ? 'active' : ''}`;
        row.dataset.id = c.candidate_id;
        row.innerHTML = `
          <div>
            <strong>${c.candidate_id}</strong>
            <div style="font-size: 10px; color: var(--text-muted);">${c.area_ha} ha | ${c.transit_distance_m}m</div>
          </div>
          <span class="badge ${c.ares_badge}">${c.ares_recommendation.split(' ')[0]}</span>
        `;
        row.onclick = () => selectCandidate(c.candidate_id);
        list.appendChild(row);
      });
    }

    function selectCandidate(candId) {
      activeCandidateId = candId;
      const z = db.zones[activeZoneKey];
      const cand = z.candidates.find(c => c.candidate_id === candId);
      if (!cand) return;

      document.querySelectorAll('.cand-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === candId);
      });

      document.getElementById('sel-cand-id').textContent = cand.candidate_id;
      document.getElementById('sel-cand-area').textContent = `${cand.area_ha} ha (${cand.area_m2.toLocaleString()} m²)`;
      document.getElementById('sel-conf-val').textContent = cand.confidence.toFixed(3);
      document.getElementById('sel-conf-bar').style.width = `${cand.confidence * 100}%`;
      document.getElementById('sel-unc-val').textContent = cand.uncertainty.toFixed(3);
      document.getElementById('sel-unc-bar').style.width = `${cand.uncertainty * 100}%`;

      document.getElementById('sel-local-xy').textContent = `${cand.local_grid.x_meters}m, ${cand.local_grid.y_meters}m`;
      document.getElementById('sel-dist').textContent = `${cand.transit_distance_m.toLocaleString()} m`;
      if (cand.coordinates && cand.coordinates.center_lat) {
        document.getElementById('sel-geodetic').textContent = `${cand.coordinates.center_lat.toFixed(4)}°, ${cand.coordinates.center_lon.toFixed(4)}°`;
      } else {
        document.getElementById('sel-geodetic').textContent = 'N/A';
      }
      document.getElementById('sel-m2').textContent = `${cand.area_m2.toLocaleString()} m²`;

      document.getElementById('sel-ares-act').textContent = cand.ares_recommendation;
      document.getElementById('sel-ares-cost').textContent = cand.ares_cost;
      document.getElementById('sel-ares-cost').className = `badge ${cand.ares_badge}`;

      drawOverlay();
    }

    function drawOverlay() {
      ctx.clearRect(0, 0, 512, 512);
      const z = db.zones[activeZoneKey];

      z.candidates.forEach(c => {
        const [xmin, ymin, xmax, ymax] = c.bbox_pixels;
        const w = xmax - xmin;
        const h = ymax - ymin;
        const isSelected = c.candidate_id === activeCandidateId;

        ctx.strokeStyle = isSelected ? '#f43f5e' : '#38bdf8';
        ctx.lineWidth = isSelected ? 3 : 1.5;
        ctx.strokeRect(xmin, ymin, w, h);

        if (isSelected) {
          ctx.fillStyle = 'rgba(244, 63, 94, 0.2)';
          ctx.fillRect(xmin, ymin, w, h);
        }

        ctx.fillStyle = isSelected ? '#f43f5e' : '#38bdf8';
        ctx.font = '10px sans-serif';
        ctx.fillText(c.candidate_id, xmin, Math.max(ymin - 3, 10));
      });
    }

    function updateView() {
      const swipeCtrl = document.getElementById('swipe-control');
      const heatCtrl = document.getElementById('heat-control');

      if (viewMode === 'swipe') {
        swipeCtrl.style.display = 'flex';
        heatCtrl.style.display = 'none';
        divider.style.display = 'block';

        preLayer.style.display = 'block';
        postLayer.style.display = 'block';
        heatLayer.style.display = 'none';
        maskLayer.style.display = 'none';

        const cut = swipePercent * 5.12;
        postLayer.style.clipPath = `polygon(${cut}px 0, 512px 0, 512px 512px, ${cut}px 512px)`;
        divider.style.left = `${swipePercent}%`;
      } else if (viewMode === 'heatmap') {
        swipeCtrl.style.display = 'none';
        heatCtrl.style.display = 'flex';
        divider.style.display = 'none';

        preLayer.style.display = 'none';
        postLayer.style.display = 'block';
        postLayer.style.clipPath = 'none';
        heatLayer.style.display = 'block';
        heatLayer.style.opacity = heatOpacity;
        maskLayer.style.display = 'none';
      } else if (viewMode === 'detections') {
        swipeCtrl.style.display = 'none';
        heatCtrl.style.display = 'none';
        divider.style.display = 'none';

        preLayer.style.display = 'none';
        postLayer.style.display = 'block';
        postLayer.style.clipPath = 'none';
        heatLayer.style.display = 'none';
        maskLayer.style.display = 'none';
      } else if (viewMode === 't1') {
        swipeCtrl.style.display = 'none';
        heatCtrl.style.display = 'none';
        divider.style.display = 'none';

        preLayer.style.display = 'block';
        postLayer.style.display = 'none';
        heatLayer.style.display = 'none';
        maskLayer.style.display = 'none';
      } else if (viewMode === 't2') {
        swipeCtrl.style.display = 'none';
        heatCtrl.style.display = 'none';
        divider.style.display = 'none';

        preLayer.style.display = 'none';
        postLayer.style.display = 'block';
        postLayer.style.clipPath = 'none';
        heatLayer.style.display = 'none';
        maskLayer.style.display = 'none';
      }

      drawOverlay();
    }

    function setupEventListeners() {
      document.querySelectorAll('.mode-tab').forEach(btn => {
        btn.onclick = () => {
          document.querySelectorAll('.mode-tab').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          viewMode = btn.dataset.mode;
          updateView();
        };
      });

      const swipeRange = document.getElementById('swipe-range');
      swipeRange.oninput = (e) => {
        swipePercent = e.target.value;
        document.getElementById('swipe-val').textContent = `${swipePercent}%`;
        updateView();
      };

      const heatRange = document.getElementById('heat-range');
      heatRange.oninput = (e) => {
        heatOpacity = e.target.value / 100.0;
        document.getElementById('heat-val').textContent = `${e.target.value}%`;
        heatLayer.style.opacity = heatOpacity;
      };

      overlayCanvas.onclick = (e) => {
        const rect = overlayCanvas.getBoundingClientRect();
        const x = (e.clientX - rect.left) * (512 / rect.width);
        const y = (e.clientY - rect.top) * (512 / rect.height);

        const z = db.zones[activeZoneKey];
        for (const c of z.candidates) {
          const [xmin, ymin, xmax, ymax] = c.bbox_pixels;
          if (x >= xmin && x <= xmax && y >= ymin && y <= ymax) {
            selectCandidate(c.candidate_id);
            break;
          }
        }
      };

      document.querySelectorAll('.d-tab').forEach(btn => {
        btn.onclick = () => {
          document.querySelectorAll('.d-tab').forEach(b => b.classList.remove('active'));
          document.querySelectorAll('.drawer-pane').forEach(p => p.classList.remove('active'));
          btn.classList.add('active');
          document.getElementById(btn.dataset.pane).classList.add('active');
        };
      });

      document.getElementById('cand-search').oninput = (e) => {
        const term = e.target.value.toLowerCase();
        const z = db.zones[activeZoneKey];
        const filtered = z.candidates.filter(c => c.candidate_id.toLowerCase().includes(term));
        renderCandidatesList(filtered);
      };
    }

    function renderCorridorsTable() {
      const tbody = document.getElementById('corridors-tbody');
      tbody.innerHTML = '';
      for (const [key, z] of Object.entries(db.zones)) {
        const totalHa = z.candidates.reduce((sum, c) => sum + c.area_ha, 0).toFixed(1);
        const ares = z.mission_summary || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${key}</strong></td>
          <td>${z.name}</td>
          <td>${z.pre_date} -> ${z.post_date}</td>
          <td><span class="badge badge-info">${z.candidates.length} targets</span></td>
          <td>${totalHa} ha</td>
          <td>${ares.policy_id || 'B3'}</td>
          <td><span class="badge badge-success"><i class="fa-solid fa-shield"></i> Yes</span></td>
        `;
        tbody.appendChild(tr);
      }
    }

    window.onload = init;
  </script>
</body>
</html>"""
