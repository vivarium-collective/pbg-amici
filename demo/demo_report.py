"""Demo: pbg-amici multi-configuration ODE report.

Runs three composite generators (exponential decay, Lotka-Volterra,
MAPK cascade) end-to-end through AMICI's real sundials/CVODES bridge,
then builds a single self-contained HTML report with sticky nav, metric
cards, Plotly time-series charts, bigraph-viz2 architecture diagrams, and
a collapsible PBG document tree.
"""

from __future__ import annotations

import html
import json
import os
import time
import webbrowser
from pathlib import Path

# Keep the demo's compile cache local to the repo so it survives across
# runs without polluting $HOME.
os.environ.setdefault(
    "AMICI_MODELS_ROOT", str(Path(__file__).resolve().parent / ".amici_cache")
)

from process_bigraph import Composite, allocate_core, gather_emitter_results

from pbg_amici import AmiciProcess  # noqa: F401  -- triggers process registration
from pbg_amici.composites.exponential_decay import exponential_decay
from pbg_amici.composites.lotka_volterra import lotka_volterra
from pbg_amici.composites.mapk_cascade import mapk_cascade


# ── Configs ─────────────────────────────────────────────────────────

CONFIGS = [
    {
        "id": "decay",
        "title": "Exponential Decay",
        "subtitle": "First-order decay of a single species",
        "description": (
            "A one-state ODE — dA/dt = -k·A — integrated by AMICI's CVODES "
            "backend. Demonstrates the simplest possible AMICI bridge round-"
            "trip: compile an antimony source, push state in each step, "
            "read the integrated trajectory back as bigraph deltas."
        ),
        "generator": exponential_decay,
        "kwargs": {"interval": 0.5, "k": 0.3, "A0": 25.0},
        "total_time": 20.0,
        "accent": "#6366f1",  # indigo
    },
    {
        "id": "lv",
        "title": "Lotka-Volterra",
        "subtitle": "Predator-prey oscillator",
        "description": (
            "Classical Lotka-Volterra dynamics. Two coupled nonlinear ODEs "
            "produce sustained oscillations; AMICI also returns two derived "
            "observables (predator/prey ratio, total population). The "
            "wrapper preserves the cyclic structure of phase space across "
            "every bigraph step boundary."
        ),
        "generator": lotka_volterra,
        "kwargs": {
            "interval": 0.25,
            "alpha": 1.1,
            "beta": 0.4,
            "d_gain": 0.1,
            "d_death": 0.4,
            "prey0": 10.0,
            "predator0": 5.0,
        },
        "total_time": 40.0,
        "accent": "#059669",  # emerald
    },
    {
        "id": "mapk",
        "title": "MAPK Cascade",
        "subtitle": "Three-tier signaling amplifier",
        "description": (
            "A simplified MAPK cascade (KKK → KK → K) with explicit "
            "phosphatases. A unit input signal is amplified by the "
            "cascading kinetic structure: K reaches a steady-state value "
            "an order of magnitude above the input. Demonstrates "
            "multi-species coupling and pseudo-steady-state behavior."
        ),
        "generator": mapk_cascade,
        "kwargs": {"interval": 1.0, "signal": 1.0, "k1": 0.05, "k2": 0.15, "k3": 0.15},
        "total_time": 80.0,
        "accent": "#ea580c",  # orange
    },
]


# ── Simulation runner ───────────────────────────────────────────────


def run_config(cfg: dict) -> dict:
    core = allocate_core()
    # Defensive register_link — discovery may not pick up AmiciProcess in
    # every environment (depends on package metadata + egg-info).
    try:
        core.register_link("AmiciProcess", AmiciProcess)
    except Exception:
        pass

    doc = cfg["generator"](core=core, **cfg["kwargs"])
    sim = Composite({"state": doc}, core=core)

    t0 = time.perf_counter()
    sim.run(cfg["total_time"])
    wall = time.perf_counter() - t0

    raw_results = gather_emitter_results(sim)
    series = next(iter(raw_results.values()))

    times = [float(s.get("time", i)) for i, s in enumerate(series)]
    state_keys = sorted(series[-1].get("states", {}).keys()) if series else []
    obs_keys = sorted(series[-1].get("observables", {}).keys()) if series else []
    states = {
        k: [float(s.get("states", {}).get(k, 0.0)) for s in series]
        for k in state_keys
    }
    observables = {
        k: [float(s.get("observables", {}).get(k, 0.0)) for s in series]
        for k in obs_keys
    }

    return {
        "cfg": cfg,
        "doc": doc,
        "times": times,
        "states": states,
        "observables": observables,
        "wall_seconds": wall,
        "n_snapshots": len(series),
    }


# ── HTML builders ───────────────────────────────────────────────────


def _plotly_traces_div(div_id: str, times, series_dict, accent, title):
    traces = []
    palette = [
        accent,
        "#0ea5e9",
        "#a855f7",
        "#f59e0b",
        "#10b981",
        "#ef4444",
        "#6b7280",
    ]
    for i, (name, ys) in enumerate(series_dict.items()):
        traces.append(
            {
                "x": times,
                "y": ys,
                "type": "scatter",
                "mode": "lines",
                "name": name,
                "line": {"width": 2.4, "color": palette[i % len(palette)]},
            }
        )
    layout = {
        "title": {"text": title, "font": {"size": 14}},
        "margin": {"l": 56, "r": 16, "t": 40, "b": 40},
        "xaxis": {"title": "time"},
        "yaxis": {"title": "value"},
        "legend": {"orientation": "h", "y": -0.22},
        "paper_bgcolor": "white",
        "plot_bgcolor": "#f8fafc",
        "height": 360,
    }
    return f"""
    <div id="{div_id}" style="width:100%;height:360px;"></div>
    <script>
      Plotly.newPlot("{div_id}",
        {json.dumps(traces)},
        {json.dumps(layout)},
        {{displayModeBar: false, responsive: true}});
    </script>
    """


def _pbg_doc_tree(doc, prefix="", depth=0):
    """Render a PBG document as collapsible HTML."""
    if isinstance(doc, dict):
        if not doc:
            return '<span style="color:#94a3b8">{}</span>'
        items = []
        for k, v in doc.items():
            key_html = (
                f'<span style="color:#7c3aed">"{html.escape(str(k))}"</span>'
            )
            child = _pbg_doc_tree(v, prefix + str(k) + ".", depth + 1)
            items.append(f"<li>{key_html}: {child}</li>")
        collapsed = " open" if depth < 2 else ""
        return (
            f"<details{collapsed}>"
            f"<summary>{{ {len(doc)} keys }}</summary>"
            f'<ul style="list-style:none;padding-left:14px">{"".join(items)}</ul>'
            f"</details>"
        )
    if isinstance(doc, list):
        if all(not isinstance(x, (dict, list)) for x in doc) and len(doc) <= 6:
            return (
                f'<span style="color:#1e293b">[{", ".join(_pbg_leaf(x) for x in doc)}]</span>'
            )
        items = "".join(
            f"<li>{_pbg_doc_tree(x, prefix + f'[{i}].', depth + 1)}</li>"
            for i, x in enumerate(doc)
        )
        collapsed = " open" if depth < 2 else ""
        return (
            f"<details{collapsed}>"
            f"<summary>[ {len(doc)} items ]</summary>"
            f'<ul style="list-style:none;padding-left:14px">{items}</ul>'
            f"</details>"
        )
    return _pbg_leaf(doc)


def _pbg_leaf(v):
    if isinstance(v, str):
        # Long antimony / SBML strings: truncate in the tree.
        s = v if len(v) <= 80 else v[:77] + "…"
        return f'<span style="color:#059669">"{html.escape(s)}"</span>'
    if isinstance(v, bool):
        return f'<span style="color:#d97706">{str(v).lower()}</span>'
    if isinstance(v, (int, float)):
        return f'<span style="color:#2563eb">{v}</span>'
    if v is None:
        return '<span style="color:#94a3b8">null</span>'
    return f'<span>{html.escape(str(v))}</span>'


def _bigraph_diagram(doc, *, dedupe: bool, height="420px") -> str:
    try:
        from bigraph_viz2 import emit_html as bv_emit

        return bv_emit(doc, height=height, inspector=True, dedupe=dedupe)
    except Exception as exc:
        return (
            f'<div style="padding:12px;background:#fef2f2;border:1px solid #fecaca;'
            f'color:#991b1b;border-radius:6px">bigraph diagram unavailable: '
            f"{html.escape(str(exc))}</div>"
        )


def build_section(result: dict, dedupe_bigraph: bool) -> str:
    cfg = result["cfg"]
    acc = cfg["accent"]
    states_div = _plotly_traces_div(
        f"chart_states_{cfg['id']}",
        result["times"],
        result["states"],
        acc,
        title="States",
    )
    obs_div = (
        _plotly_traces_div(
            f"chart_obs_{cfg['id']}",
            result["times"],
            result["observables"],
            acc,
            title="Observables",
        )
        if result["observables"]
        else '<div style="color:#94a3b8;padding:1em">(no observables)</div>'
    )

    bigraph_html = _bigraph_diagram(result["doc"], dedupe=dedupe_bigraph)
    doc_tree = _pbg_doc_tree(result["doc"])

    final_state = {k: vs[-1] for k, vs in result["states"].items()}
    final_obs = {k: vs[-1] for k, vs in result["observables"].items()}

    metric_card = lambda label, value: f"""
      <div class="metric">
        <div class="metric-label">{html.escape(label)}</div>
        <div class="metric-value">{html.escape(str(value))}</div>
      </div>"""

    final_state_pretty = ", ".join(
        f"{k}={v:.3g}" for k, v in final_state.items()
    ) or "—"
    final_obs_pretty = ", ".join(
        f"{k}={v:.3g}" for k, v in final_obs.items()
    ) or "—"

    return f"""
    <section id="{cfg['id']}" style="border-top: 4px solid {acc};">
      <header>
        <h2 style="color:{acc}">{html.escape(cfg['title'])}</h2>
        <div class="subtitle">{html.escape(cfg['subtitle'])}</div>
        <p class="desc">{html.escape(cfg['description'])}</p>
      </header>

      <div class="metric-row">
        {metric_card("Snapshots", result["n_snapshots"])}
        {metric_card("Total time", f"{cfg['total_time']:.1f}")}
        {metric_card("Wall clock (s)", f"{result['wall_seconds']:.2f}")}
        {metric_card("Final states", final_state_pretty)}
        {metric_card("Final observables", final_obs_pretty)}
      </div>

      <div class="grid">
        <div class="card">
          <h3>State trajectories</h3>
          {states_div}
        </div>
        <div class="card">
          <h3>Observables</h3>
          {obs_div}
        </div>
      </div>

      <div class="card">
        <h3>Bigraph architecture</h3>
        {bigraph_html}
      </div>

      <div class="card">
        <h3>PBG document</h3>
        <div class="doc-tree">{doc_tree}</div>
      </div>
    </section>
    """


def build_report(results: list[dict], output_path: Path) -> None:
    sections = []
    for i, r in enumerate(results):
        sections.append(build_section(r, dedupe_bigraph=(i > 0)))

    nav_items = "".join(
        f'<a href="#{r["cfg"]["id"]}" style="border-bottom:3px solid {r["cfg"]["accent"]}">{html.escape(r["cfg"]["title"])}</a>'
        for r in results
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>pbg-amici demo report</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px 28px 80px;
      background: #ffffff;
      color: #1e293b;
      line-height: 1.5;
    }}
    h1 {{ font-size: 28px; margin: 8px 0 4px; }}
    .subtitle, .lede {{ color: #64748b; }}
    .lede {{ font-size: 15px; max-width: 780px; margin-bottom: 18px; }}
    nav.sticky {{
      position: sticky;
      top: 0;
      background: rgba(255,255,255,0.95);
      backdrop-filter: blur(6px);
      padding: 10px 0;
      margin: 6px 0 24px;
      display: flex;
      gap: 20px;
      border-bottom: 1px solid #e2e8f0;
      z-index: 10;
    }}
    nav.sticky a {{
      text-decoration: none;
      color: #1e293b;
      font-weight: 500;
      padding-bottom: 2px;
    }}
    section {{
      padding: 22px 0 8px;
      margin-bottom: 28px;
    }}
    section header h2 {{ margin: 6px 0 2px; font-size: 22px; }}
    section header .subtitle {{ font-size: 14px; }}
    .desc {{ max-width: 760px; margin: 10px 0 18px; color: #334155; }}
    .metric-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin: 16px 0;
    }}
    .metric {{
      flex: 1 1 160px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px 14px;
    }}
    .metric-label {{ font-size: 11px; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; }}
    .metric-value {{ font-size: 16px; color: #0f172a; font-weight: 600; margin-top: 4px; word-break: break-word; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
      gap: 14px;
      margin: 14px 0;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 16px 18px;
      margin: 12px 0;
    }}
    .card h3 {{ margin: 0 0 8px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #475569; }}
    .doc-tree {{
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
      font-size: 12.5px;
      max-height: 360px;
      overflow: auto;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 10px;
    }}
    .doc-tree details summary {{ cursor: pointer; color: #475569; }}
  </style>
</head>
<body>
  <h1>pbg-amici demo report</h1>
  <p class="lede">
    Three composite generators driven through AMICI's real sundials/CVODES
    bridge — each compiled per-model and integrated step-by-step through
    process-bigraph's runtime. All bridge round-trips push upstream state
    into AMICI and emit per-key deltas, so downstream composers can attach
    controllers, dosing schedules, or calibration offsets to the same stores.
  </p>
  <nav class="sticky">{nav_items}</nav>
  {''.join(sections)}
</body>
</html>"""

    output_path.write_text(html_doc)


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    here = Path(__file__).resolve().parent
    results = []
    for cfg in CONFIGS:
        print(f"  running {cfg['id']!r:14s}", end="", flush=True)
        r = run_config(cfg)
        print(
            f" ✓  {r['n_snapshots']:>3d} snapshots, "
            f"{r['wall_seconds']:.2f}s wall"
        )
        results.append(r)
    output = here / "report.html"
    build_report(results, output)
    print(f"\nwrote {output} ({output.stat().st_size // 1024} KB)")
    webbrowser.open("file://" + str(output))


if __name__ == "__main__":
    main()
