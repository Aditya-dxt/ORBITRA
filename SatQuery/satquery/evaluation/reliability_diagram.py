"""Calibration Reliability Diagram Generator for SatQuery.

Computes bin-level calibration statistics and renders publication-grade
ASCII and SVG reliability diagrams comparing predicted confidence vs. empirical accuracy.
"""

from typing import Dict, List, Tuple
import numpy as np


def compute_reliability_data(
    probabilities: np.ndarray,
    ground_truth: np.ndarray,
    num_bins: int = 10
) -> Dict:
    """Compute bin-by-bin calibration metrics for a reliability diagram.

    Args:
        probabilities: Calibrated probabilities p_i in [0.0, 1.0].
        ground_truth: Binary true labels y_i in {0, 1}.
        num_bins: Number of equal-width probability bins (default 10).

    Returns:
        Dict containing bin table, ECE, MCE, and Brier score.
    """
    probs = np.asarray(probabilities, dtype=np.float64).ravel()
    labels = np.asarray(ground_truth, dtype=np.float64).ravel()
    n = len(probs)
    if n == 0:
        return {"bins": [], "ece": 0.0, "mce": 0.0, "brier_score": 0.0, "num_samples": 0}

    brier_score = float(np.mean((probs - labels) ** 2))
    bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
    bins = []
    ece = 0.0
    mce = 0.0

    for i in range(num_bins):
        b_low = bin_edges[i]
        b_high = bin_edges[i + 1]

        if i == num_bins - 1:
            in_bin = (probs >= b_low) & (probs <= b_high)
        else:
            in_bin = (probs >= b_low) & (probs < b_high)

        count = int(np.sum(in_bin))
        if count > 0:
            bin_acc = float(np.mean(labels[in_bin]))
            bin_conf = float(np.mean(probs[in_bin]))
            gap = abs(bin_acc - bin_conf)
            ece += (count / n) * gap
            mce = max(mce, gap)
        else:
            bin_acc = 0.0
            bin_conf = float((b_low + b_high) / 2.0)
            gap = 0.0

        bins.append({
            "bin_index": i + 1,
            "bin_range": f"[{b_low:.1f}, {b_high:.1f}]",
            "bin_center": round((b_low + b_high) / 2.0, 3),
            "count": count,
            "sample_weight": round(count / n, 4),
            "confidence": round(bin_conf, 4),
            "accuracy": round(bin_acc, 4),
            "gap": round(gap, 4),
        })

    return {
        "bins": bins,
        "ece": round(float(ece), 4),
        "mce": round(float(mce), 4),
        "brier_score": round(float(brier_score), 4),
        "num_samples": n,
    }


def render_ascii_reliability_diagram(rel_data: Dict) -> str:
    """Render an ASCII visual representation of the reliability diagram."""
    lines = []
    lines.append("=" * 72)
    lines.append("📈 RELIABILITY DIAGRAM: EMPIRICAL ACCURACY vs. PREDICTED CONFIDENCE")
    lines.append("=" * 72)
    lines.append(f"{'Bin Range':<12} | {'Count':<6} | {'Conf (p)':<9} | {'Acc (y)':<9} | {'Gap |p-y|':<9} | {'Visual Alignment'}")
    lines.append("-" * 72)

    width = 20
    for b in rel_data["bins"]:
        c = b["confidence"]
        a = b["accuracy"]
        gap = b["gap"]
        cnt = b["count"]
        brange = b["bin_range"]

        if cnt == 0:
            bar = "[      EMPTY       ]"
        else:
            c_pos = min(width - 1, max(0, int(c * width)))
            a_pos = min(width - 1, max(0, int(a * width)))
            chars = [" "] * width
            # Mark ideal diagonal anchor
            diag_pos = min(width - 1, max(0, int(b["bin_center"] * width)))
            chars[diag_pos] = "."

            if c_pos == a_pos:
                chars[c_pos] = "O"  # Perfect match
            else:
                chars[c_pos] = "C"  # Confidence
                chars[a_pos] = "A"  # Accuracy
                min_p, max_p = min(c_pos, a_pos), max(c_pos, a_pos)
                for p in range(min_p + 1, max_p):
                    if chars[p] == " ":
                        chars[p] = "-"

            bar = "[" + "".join(chars) + "]"

        lines.append(f"{brange:<12} | {cnt:<6} | {c:<9.3f} | {a:<9.3f} | {gap:<9.3f} | {bar}")

    lines.append("-" * 72)
    lines.append(f"Legend: 'O' = Calibrated Match | 'C' = Confidence | 'A' = Accuracy | '.' = Ideal (y=x)")
    lines.append(f"Summary: ECE = {rel_data['ece']:.4f} | MCE = {rel_data['mce']:.4f} | Brier = {rel_data['brier_score']:.4f} (N={rel_data['num_samples']})")
    lines.append("=" * 72)
    return "\n".join(lines)


def generate_svg_reliability_diagram(rel_data: Dict, output_path: str) -> None:
    """Export a clean vector SVG graphic of the reliability diagram."""
    w, h = 600, 480
    margin = 60
    plot_w = w - 2 * margin
    plot_h = h - 2 * margin

    ece = rel_data["ece"]
    brier = rel_data["brier_score"]
    status = "Well-Calibrated (ECE < 0.10)" if ece < 0.10 else "High ECE"

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif;">',
        '<!-- Header -->',
        f'<text x="{w/2}" y="32" text-anchor="middle" font-size="16" font-weight="bold" fill="#1e293b">SatQuery Confidence Calibration: Reliability Diagram</text>',
        f'<text x="{w/2}" y="50" text-anchor="middle" font-size="12" fill="#64748b">Held-Out Test Set (ECE: {ece:.4f} | Brier: {brier:.4f} | Status: {status})</text>',
        '<!-- Plot Area Background -->',
        f'<rect x="{margin}" y="{margin}" width="{plot_w}" height="{plot_h}" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>',
        '<!-- Grid Lines -->',
    ]

    for val in np.linspace(0.0, 1.0, 11):
        x = margin + val * plot_w
        y = margin + (1.0 - val) * plot_h
        svg_parts.append(f'<line x1="{x}" y1="{margin}" x2="{x}" y2="{margin+plot_h}" stroke="#e2e8f0" stroke-width="1"/>')
        svg_parts.append(f'<line x1="{margin}" y1="{y}" x2="{margin+plot_w}" y2="{y}" stroke="#e2e8f0" stroke-width="1"/>')
        svg_parts.append(f'<text x="{x}" y="{margin+plot_h+16}" text-anchor="middle" font-size="10" fill="#64748b">{val:.1f}</text>')
        svg_parts.append(f'<text x="{margin-8}" y="{y+3}" text-anchor="end" font-size="10" fill="#64748b">{val:.1f}</text>')

    # Ideal Diagonal (y = x)
    svg_parts.append(f'<line x1="{margin}" y1="{margin+plot_h}" x2="{margin+plot_w}" y2="{margin}" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6,4"/>')

    # Calibration Bars and Error Gaps
    bar_width = (plot_w / len(rel_data["bins"])) * 0.7
    for b in rel_data["bins"]:
        if b["count"] == 0:
            continue
        c = b["confidence"]
        a = b["accuracy"]

        cx = margin + c * plot_w
        cy = margin + (1.0 - a) * plot_h
        ideal_y = margin + (1.0 - c) * plot_h

        # Gap bar between predicted confidence and actual accuracy
        gap_y = min(cy, ideal_y)
        gap_h = abs(cy - ideal_y)
        if gap_h > 1:
            svg_parts.append(f'<rect x="{cx - bar_width/2}" y="{gap_y}" width="{bar_width}" height="{gap_h}" fill="rgba(239, 68, 68, 0.25)" stroke="#ef4444" stroke-width="1"/>')

        # Accuracy point
        svg_parts.append(f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="#2563eb" stroke="#ffffff" stroke-width="1.5"/>')

    # Axis Labels
    svg_parts.append(f'<text x="{margin + plot_w/2}" y="{h - 15}" text-anchor="middle" font-size="12" font-weight="600" fill="#334155">Mean Predicted Confidence (p)</text>')
    svg_parts.append(f'<text transform="rotate(-90)" x="{-margin - plot_h/2}" y="18" text-anchor="middle" font-size="12" font-weight="600" fill="#334155">Empirical True Accuracy (y)</text>')

    # Legend
    leg_x = margin + 15
    leg_y = margin + 25
    svg_parts.extend([
        f'<g transform="translate({leg_x}, {leg_y})">',
        '<line x1="0" y1="0" x2="20" y2="0" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>',
        '<text x="26" y="4" font-size="11" fill="#475569">Perfect Calibration (y = x)</text>',
        '<circle cx="10" cy="16" r="4" fill="#2563eb"/>',
        '<text x="26" y="20" font-size="11" fill="#475569">Empirical Bin Accuracy</text>',
        '<rect x="2" y="28" width="16" height="10" fill="rgba(239, 68, 68, 0.25)" stroke="#ef4444" stroke-width="1"/>',
        '<text x="26" y="37" font-size="11" fill="#475569">Calibration Error Gap</text>',
        '</g>',
        '</svg>'
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_parts))
