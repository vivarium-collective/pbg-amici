"""AMICI process-bigraph wrappers.

Real bridge to the AMICI Python package
(https://github.com/AMICI-dev/AMICI): compiles an antimony or SBML model into
AMICI's per-model C++/SWIG extension, then drives the sundials-based ODE
integrator via ``amici.sim.sundials.run_simulation``.

Three wrappers, sharing one compile/load path:

* ``AmiciProcess`` — a time-stepped, delta-emitting Process for composition
  with sibling processes.
* ``AmiciUTCStep`` — a one-shot uniform-time-course Step: SBML path + horizon +
  point count in, a ``{time, columns, values}`` trajectory out. This is the
  shape multi-simulator comparison harnesses (e.g. pbg-biomodels) consume.
* ``AmiciSteadyStateStep`` — a one-shot Step that integrates to steady state
  (AMICI's ``t = inf`` timepoint) and emits the final observable values.

Imports of ``amici`` are lazy so the module stays importable (and editable)
before ``amici`` / ``antimony`` are installed; the import only fires inside
``update()`` / ``_load_model()``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from process_bigraph import Process, Step


def _hash_source(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Shared compile / load helpers — used by AmiciProcess and the one-shot Steps. #
# --------------------------------------------------------------------------- #


def _resolve_source(config: dict) -> tuple[str, str]:
    """Return ``(kind, source_text)`` for the configured model.

    ``kind`` is ``"antimony"`` or ``"sbml"``. Exactly one of
    ``antimony`` / ``sbml`` / ``sbml_file`` must be set.
    """
    ant = config.get("antimony") or ""
    sbml = config.get("sbml") or ""
    sbml_file = config.get("sbml_file") or ""
    provided = [bool(ant), bool(sbml), bool(sbml_file)]
    if sum(provided) != 1:
        raise ValueError(
            "AmiciProcess requires exactly one of config['antimony'], "
            "config['sbml'], or config['sbml_file']."
        )
    if ant:
        return "antimony", ant
    if sbml:
        return "sbml", sbml
    return "sbml", Path(sbml_file).read_text()


def _compile_model(
    kind: str, source: str, model_id: str, model_dir: Path, verbose: bool
) -> None:
    if kind == "antimony":
        from amici.importers.antimony import antimony2amici

        antimony2amici(
            source, model_name=model_id, output_dir=str(model_dir), verbose=verbose,
        )
        return

    # SBML: a filesystem path is compiled directly; an inline string is
    # written to a temp file first.
    from amici import SbmlImporter

    if os.path.isfile(source):
        sbml_path = source
    else:
        sbml_path = str(model_dir / "model.sbml")
        Path(sbml_path).write_text(source)
    importer = SbmlImporter(sbml_path)
    importer.sbml2amici(
        model_name=model_id, output_dir=str(model_dir), verbose=verbose,
    )


def _load_model(config: dict):
    """Compile (if needed) and load the AMICI model module for ``config``.

    Returns ``(module, model)``. The compiled extension is cached under
    AMICI's per-model dir, so repeated calls for the same source are fast.
    """
    # NB: the model's swig-generated __init__.py references
    # ``amici.sim.sundials`` as an attribute on the ``amici`` package, so that
    # submodule must be imported before loading the model module.
    import amici
    import amici.sim.sundials  # noqa: F401  -- ensures attribute resolves
    from amici import import_model_module

    kind, source = _resolve_source(config)
    model_id = config.get("model_id") or f"amici_{kind}_{_hash_source(source)}"

    model_dir = config.get("model_dir") or str(amici.get_model_dir(model_id))
    model_dir_p = Path(model_dir)
    model_dir_p.mkdir(parents=True, exist_ok=True)
    compiled_init = model_dir_p / model_id / "__init__.py"
    if not compiled_init.is_file():
        _compile_model(
            kind, source, model_id, model_dir_p,
            verbose=not config.get("quiet_compile", True),
        )

    mod = import_model_module(model_id, str(model_dir_p))
    return mod, mod.get_model()


def _configure_solver(solver, config: dict) -> None:
    """Apply the common CVODES knobs to an AMICI solver (version-tolerant)."""
    rtol = float(config.get("rtol", 1e-8))
    atol = float(config.get("atol", 1e-16))
    max_steps = int(config.get("max_steps", 10000))
    for setter, value in (
        ("set_relative_tolerance", rtol),
        ("set_absolute_tolerance", atol),
        ("set_max_steps", max_steps),
    ):
        fn = getattr(solver, setter, None)
        if fn is not None:
            fn(value)


# Solver-knob config keys shared by the one-shot Steps (and AmiciProcess).
_SOLVER_CONFIG_SCHEMA = {
    "model_id": {"_type": "string", "_default": ""},
    "model_dir": {"_type": "string", "_default": ""},
    "rtol": {"_type": "float", "_default": 1e-8},
    "atol": {"_type": "float", "_default": 1e-16},
    "max_steps": {"_type": "integer", "_default": 10000},
    "quiet_compile": {"_type": "boolean", "_default": True},
}


class AmiciProcess(Process):
    """Time-stepped ODE simulation via AMICI.

    Each ``update(state, interval)`` integrates the underlying model from the
    current state (read from the input ``states`` port) for ``interval`` time
    units using AMICI's sundials backend, then emits per-species deltas on
    the output ``states`` port and per-observable deltas on ``observables``.
    Free parameters and fixed parameters can be driven by sibling processes
    via the input ``parameters`` / ``fixed_parameters`` ports.

    Bare ``map[string,float]`` outputs (not ``overwrite[...]``) so updates
    compose additively with sibling processes — a kinetic perturbation, a
    bolus dose, or a calibration offset can all write the same store.
    """

    config_schema = {
        # Antimony source code, OR an SBML XML string, OR a filesystem path.
        # Exactly one of ``antimony`` / ``sbml`` / ``sbml_file`` is required.
        "antimony": {"_type": "string", "_default": ""},
        "sbml": {"_type": "string", "_default": ""},
        "sbml_file": {"_type": "string", "_default": ""},
        **_SOLVER_CONFIG_SCHEMA,
    }

    def __init__(self, config: dict | None = None, core: Any = None):
        super().__init__(config=config, core=core)
        self._mod = None
        self._model = None
        self._solver = None
        # Bigraph-side names are the clean human-readable ones AMICI exposes
        # via ``get_*_names()`` (e.g. ``k``); AMICI internally identifies
        # parameters by prefixed ids (e.g. ``amici_k``) but its setters are
        # positional, so we only need the ordered name lists.
        self._state_ids: list[str] = []
        self._free_param_names: list[str] = []
        self._fixed_param_names: list[str] = []
        self._obs_ids: list[str] = []
        # Deltas are emitted relative to the value we returned last step;
        # for observables (a derived signal) we cache the previous reading.
        self._prev_obs: dict[str, float] = {}
        self._compiled = False

    # ------------------------------------------------------------------ ports

    def inputs(self) -> dict[str, str]:
        # Every input is something a sibling process could plausibly write
        # to this model: the current absolute state of each species, a
        # current setting for each free/fixed parameter (controllers,
        # calibrators), or an external override. Defaults come from the
        # compiled model via initial_state().
        return {
            "states": "map[string,float]",
            "parameters": "map[string,float]",
            "fixed_parameters": "map[string,float]",
        }

    def outputs(self) -> dict[str, str]:
        # Bare map[string,float] so a sibling growth/dose/division process
        # can also contribute to the same store. Each value is a delta
        # versus what the store currently holds.
        return {
            "states": "map[string,float]",
            "observables": "map[string,float]",
        }

    # --------------------------------------------------------- initialization

    def initial_state(self) -> dict[str, Any]:
        self._ensure_compiled()
        x0 = list(self._model.get_initial_state())
        free_params = list(self._model.get_free_parameters())
        fixed_params = list(self._model.get_fixed_parameters())
        return {
            "states": {sid: float(x0[i]) for i, sid in enumerate(self._state_ids)},
            "parameters": {
                name: float(free_params[i])
                for i, name in enumerate(self._free_param_names)
            },
            "fixed_parameters": {
                name: float(fixed_params[i])
                for i, name in enumerate(self._fixed_param_names)
            },
        }

    # ------------------------------------------------------------- compile +

    def _ensure_compiled(self) -> None:
        if self._compiled:
            return

        self._mod, self._model = _load_model(self.config)
        self._solver = self._model.create_solver()
        _configure_solver(self._solver, self.config)

        self._state_ids = list(self._model.get_state_ids())
        self._free_param_names = list(self._model.get_free_parameter_names())
        self._fixed_param_names = list(self._model.get_fixed_parameter_names())
        self._obs_ids = list(self._model.get_observable_ids())
        self._prev_obs = {oid: 0.0 for oid in self._obs_ids}
        self._compiled = True

    # ----------------------------------------------------------------- update

    def update(self, state: dict[str, Any], interval: float) -> dict[str, Any]:
        self._ensure_compiled()
        from amici.sim.sundials import run_simulation

        # 1. Push upstream-driven state into the model.
        current_states = dict(state.get("states") or {})
        current_params = dict(state.get("parameters") or {})
        current_fixed = dict(state.get("fixed_parameters") or {})

        x0 = [
            float(current_states.get(sid, 0.0))
            for sid in self._state_ids
        ]
        self._model.set_initial_state(x0)

        if current_params and self._free_param_names:
            defaults_free = list(self._model.get_free_parameters())
            p = [
                float(current_params.get(name, defaults_free[i]))
                for i, name in enumerate(self._free_param_names)
            ]
            self._model.set_free_parameters(p)
        if current_fixed and self._fixed_param_names:
            defaults_fixed = list(self._model.get_fixed_parameters())
            k = [
                float(current_fixed.get(name, defaults_fixed[i]))
                for i, name in enumerate(self._fixed_param_names)
            ]
            self._model.set_fixed_parameters(k)

        # 2. Integrate from t=0 to t=interval (relative time per step).
        self._model.set_t0(0.0)
        self._model.set_timepoints([float(interval)])
        rdata = run_simulation(self._model, self._solver)
        if int(rdata.status) != 0:
            raise RuntimeError(
                f"AMICI integration failed: status={int(rdata.status)} "
                f"after interval={interval} from x0={x0}"
            )

        # 3. Read terminal state + observables back.
        x_final = rdata.x[-1] if rdata.x is not None else []
        new_states = {
            sid: float(x_final[i]) for i, sid in enumerate(self._state_ids)
        }
        state_deltas = {
            sid: new_states[sid] - float(current_states.get(sid, 0.0))
            for sid in self._state_ids
        }

        obs_deltas: dict[str, float] = {}
        if rdata.y is not None and self._obs_ids:
            y_final = rdata.y[-1]
            for i, oid in enumerate(self._obs_ids):
                current_y = float(y_final[i])
                obs_deltas[oid] = current_y - self._prev_obs.get(oid, 0.0)
                self._prev_obs[oid] = current_y

        return {"states": state_deltas, "observables": obs_deltas}


# --------------------------------------------------------------------------- #
# One-shot Steps                                                              #
# --------------------------------------------------------------------------- #


def _validate_n_points(n: Any) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError(f"AmiciUTCStep: n_points must be an integer >= 2, got {n!r}")
    if n < 2:
        raise ValueError(f"AmiciUTCStep: n_points must be >= 2, got {n}")
    return n


class AmiciUTCStep(Step):
    """One-shot uniform time course via AMICI.

    Runtime inputs (so a loader can feed them dynamically):

    * ``model_source`` — path to an SBML file.
    * ``time``         — integration horizon (t runs 0 → time).
    * ``n_points``     — number of evenly-spaced output points (>= 2).

    Emits the canonical ``{result: {time, columns, values}}`` trajectory, one
    column per AMICI state id (the species ids from the SBML). This matches the
    one-shot UTC contract consumed by multi-simulator comparison harnesses.
    """

    config_schema = dict(_SOLVER_CONFIG_SCHEMA)

    def inputs(self) -> dict[str, str]:
        return {"model_source": "string", "time": "float", "n_points": "integer"}

    def outputs(self) -> dict[str, str]:
        # ``tree`` keeps this Step self-contained — it doesn't depend on a
        # downstream ``numeric_result`` type being registered in the core.
        return {"result": "tree"}

    def _model_config(self, model_source: str) -> dict:
        # Inline-clear the other source keys so exactly one is set.
        cfg = dict(self.config)
        cfg.update(antimony="", sbml="", sbml_file=model_source)
        return cfg

    def update(self, state: dict[str, Any]) -> dict[str, Any]:
        from amici.sim.sundials import run_simulation

        n_points = _validate_n_points(state["n_points"])
        horizon = float(state["time"])

        _mod, model = _load_model(self._model_config(state["model_source"]))
        solver = model.create_solver()
        _configure_solver(solver, self.config)

        state_ids = list(model.get_state_ids())
        model.set_initial_state(list(model.get_initial_state()))
        timepoints = [horizon * i / (n_points - 1) for i in range(n_points)]
        model.set_t0(0.0)
        model.set_timepoints([float(t) for t in timepoints])

        rdata = run_simulation(model, solver)
        if int(rdata.status) != 0:
            raise RuntimeError(
                f"AMICI UTC integration failed: status={int(rdata.status)} "
                f"over horizon={horizon} with n_points={n_points}"
            )

        xs = rdata.x
        values = [
            [float(xs[r][c]) for c in range(len(state_ids))]
            for r in range(len(timepoints))
        ]
        return {
            "result": {
                "time": list(timepoints),
                "columns": state_ids,
                "values": values,
            }
        }


class AmiciSteadyStateStep(Step):
    """One-shot steady-state solve via AMICI.

    Runtime input ``model_source`` (an SBML file path). Integrates to steady
    state using AMICI's ``t = inf`` timepoint and emits the final value of
    each state id as ``{result: {kind: "steady_state", time: None,
    observables: {id: value}}}`` — the steady-state contract consumed by
    multi-simulator comparison harnesses.
    """

    config_schema = dict(_SOLVER_CONFIG_SCHEMA)

    def inputs(self) -> dict[str, str]:
        return {"model_source": "string"}

    def outputs(self) -> dict[str, str]:
        return {"result": "tree"}

    def update(self, state: dict[str, Any]) -> dict[str, Any]:
        from amici.sim.sundials import run_simulation

        cfg = dict(self.config)
        cfg.update(antimony="", sbml="", sbml_file=state["model_source"])
        _mod, model = _load_model(cfg)
        solver = model.create_solver()
        _configure_solver(solver, self.config)

        state_ids = list(model.get_state_ids())
        model.set_initial_state(list(model.get_initial_state()))
        model.set_t0(0.0)
        model.set_timepoints([float("inf")])  # AMICI solves to steady state

        rdata = run_simulation(model, solver)
        if int(rdata.status) != 0:
            raise RuntimeError(
                f"AMICI steady-state solve failed: status={int(rdata.status)}"
            )

        x_final = rdata.x[-1]
        observables = {
            sid: float(x_final[i]) for i, sid in enumerate(state_ids)
        }
        return {
            "result": {
                "kind": "steady_state",
                "time": None,
                "observables": observables,
            }
        }
