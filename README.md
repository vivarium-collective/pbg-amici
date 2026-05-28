# pbg-amici

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph)
wrapper for **AMICI** — the [Advanced Multilanguage Interface to CVODES and
IDAS](https://github.com/AMICI-dev/AMICI). AMICI compiles SBML or antimony
models into a per-model C++/SWIG Python extension backed by SUNDIALS' CVODES
ODE integrator; this package bridges that runtime as a first-class
process-bigraph `Process` so AMICI simulations can be composed with the rest
of a bigraph workflow.

This is a **real bridge**: every `update()` call drives the genuine
upstream AMICI runtime (`amici.sim.sundials.run_simulation`) — not a
re-implementation of its math and not a mock.

## Installation

```bash
# From PyPI (once released):
pip install pbg-amici

# For development (editable):
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

Once installed, `AmiciProcess` is auto-discovered by `allocate_core()` via
`bigraph_schema.package.discover` — no manual `register_link()` calls
needed.

> **AMICI build prerequisites.** AMICI compiles a C++ extension per model.
> On macOS/Linux you need a recent C++ compiler, SWIG, and BLAS (the AMICI
> wheel bundles SUNDIALS). On Apple Silicon the pip wheel installs cleanly
> on Python 3.11/3.12. See AMICI's
> [install docs](https://github.com/AMICI-dev/AMICI/blob/master/documentation/python_installation.rst)
> for distro-specific notes.

## Quick start

```python
from process_bigraph import Composite, allocate_core, gather_emitter_results
from pbg_amici.composites.lotka_volterra import lotka_volterra

core = allocate_core()
sim = Composite({"state": lotka_volterra(core=core, interval=0.25)}, core=core)
sim.run(20.0)

for path, series in gather_emitter_results(sim).items():
    print(path, "->", len(series), "snapshots")
```

The first call compiles the antimony model (≈10 s on a recent laptop); the
compiled extension is cached under `$AMICI_MODELS_ROOT/<version>/<model_id>/`
so subsequent runs reuse it.

## API reference

| Class | Kind | Inputs | Outputs |
|---|---|---|---|
| `AmiciProcess` | `Process` | `states`, `parameters`, `fixed_parameters` (all `map[string,float]`) | `states`, `observables` (both `map[string,float]` deltas) |

### `AmiciProcess` config

| Key | Type | Default | Description |
|---|---|---|---|
| `antimony` | string | `""` | Antimony source code (mutually exclusive with `sbml*`) |
| `sbml` | string | `""` | Inline SBML XML string |
| `sbml_file` | string | `""` | Path to an SBML XML file |
| `model_id` | string | derived | Stable name used for the compiled-model cache directory |
| `model_dir` | string | derived | Override the compiled-model cache directory |
| `rtol` | float | `1e-8` | CVODES relative tolerance |
| `atol` | float | `1e-16` | CVODES absolute tolerance |
| `max_steps` | int | `10000` | Max integration steps per call |
| `quiet_compile` | bool | `true` | Suppress AMICI's compile-time chatter |

Exactly one of `antimony` / `sbml` / `sbml_file` must be set.

## Architecture

```
                ┌───────────────────────────────────────────┐
   parameters ──▶                                           │
        states ──▶  AmiciProcess (bridge)                   ▶── states     (delta)
fixed_params  ──▶                                           ▶── observables (delta)
                │   ┌──────────────────────────────────┐    │
                │   │ amici.import_model_module(...)   │    │
                │   │ amici.sim.sundials.run_simulation│    │
                │   │ CVODES / SUNDIALS                │    │
                │   └──────────────────────────────────┘    │
                └───────────────────────────────────────────┘
```

On each `update(state, interval)`:

1. The bridge writes the current `states`, `parameters`, and
   `fixed_parameters` into the compiled model (`set_initial_state`,
   `set_free_parameters`, `set_fixed_parameters`).
2. AMICI integrates from `t=0` to `t=interval` via CVODES.
3. The bridge reads back `rdata.x[-1]` and `rdata.y[-1]` and emits
   per-key **deltas** against the input state, so a sibling process
   (controllers, bolus injections, calibration offsets) can also write
   the same store and the updates compose additively.

## Composites

Three dashboard-discoverable generators:

- `amici_exponential_decay` — single-species first-order decay (smoke test)
- `amici_lotka_volterra` — classical predator-prey dynamics with derived
  observables (`ratio`, `total`)
- `amici_mapk_cascade` — three-tier MAPK signaling cascade demonstrating
  signal amplification through coupled active-fraction kinetics

Each is a `@composite_generator`-decorated function and is surfaced under
the dashboard's Composites tab automatically.

## Demo

```bash
python demo/demo_report.py
# writes demo/report.html and opens it in your default browser
```

The report includes per-configuration metrics, Plotly time-series charts
for each composite, an interactive bigraph diagram, and a collapsible PBG
document tree.

## Limitations

- Each unique model source compiles a separate per-model extension; the
  first compile takes 5-15 s. The cache lives in `amici_models/`.
- This wrapper exposes the deterministic ODE integration path. AMICI's
  sensitivity analysis, parameter estimation, and JAX backend are
  upstream features that this version of the bridge does not expose
  through bigraph ports yet.
- Observable expressions are read directly from the antimony / SBML model
  (`:=` assignment rules in antimony). The bridge does not currently let
  sibling processes inject new observable formulas at runtime.

## License

MIT.
