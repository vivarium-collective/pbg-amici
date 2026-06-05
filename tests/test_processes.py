"""Unit tests for the AMICI bridge.

These hit the real upstream simulator: each test compiles a tiny antimony
model and integrates it. The compile is cached under AMICI's default model
dir so repeated runs are fast.
"""

from __future__ import annotations

import pytest

amici = pytest.importorskip("amici")
pytest.importorskip("antimony")

import math  # noqa: E402

from process_bigraph import allocate_core  # noqa: E402

from pbg_amici import AmiciProcess, AmiciUTCStep, AmiciSteadyStateStep  # noqa: E402


_DECAY = """
model exponential_decay
  A = 10
  A' = -k * A
  k = 0.2
end
"""


def test_ports_are_dicts():
    proc = AmiciProcess.__new__(AmiciProcess)  # no construction-side compile
    # Bypass __init__ — we only want to inspect the port shape.
    assert isinstance(AmiciProcess.config_schema, dict)


def test_compile_and_one_step_real_bridge():
    core = allocate_core()
    proc = AmiciProcess(
        config={"antimony": _DECAY, "model_id": "test_exp_decay_step"},
        core=core,
    )
    init = proc.initial_state()
    assert init["states"] == {"A": 10.0}
    assert init["parameters"] == {"k": 0.2}

    out = proc.update(
        {"states": {"A": 10.0}, "parameters": {"k": 0.2}, "fixed_parameters": {}},
        interval=1.0,
    )

    # A(1) under dA/dt = -0.2 A with A(0)=10 is 10 * exp(-0.2) ≈ 8.187.
    expected = 10.0 * (2.718281828 ** -0.2)
    new_A = 10.0 + out["states"]["A"]
    assert abs(new_A - expected) < 1e-3


def test_parameter_override_changes_dynamics():
    """A sibling process writing a different k must affect the integration."""
    core = allocate_core()
    proc = AmiciProcess(
        config={"antimony": _DECAY, "model_id": "test_exp_decay_param"},
        core=core,
    )
    # k=0.5 -> faster decay: A(1) = 10 * exp(-0.5) ≈ 6.065
    out = proc.update(
        {"states": {"A": 10.0}, "parameters": {"k": 0.5}, "fixed_parameters": {}},
        interval=1.0,
    )
    new_A = 10.0 + out["states"]["A"]
    expected = 10.0 * (2.718281828 ** -0.5)
    assert abs(new_A - expected) < 1e-3


def test_state_override_changes_initial_condition():
    """A sibling process writing a non-default state must seed the integration."""
    core = allocate_core()
    proc = AmiciProcess(
        config={"antimony": _DECAY, "model_id": "test_exp_decay_x0"},
        core=core,
    )
    # A0=20 -> A(1) = 20 * exp(-0.2) ≈ 16.375
    out = proc.update(
        {"states": {"A": 20.0}, "parameters": {"k": 0.2}, "fixed_parameters": {}},
        interval=1.0,
    )
    new_A = 20.0 + out["states"]["A"]
    expected = 20.0 * (2.718281828 ** -0.2)
    assert abs(new_A - expected) < 1e-3


def _decay_sbml(tmp_path) -> str:
    """Convert the antimony decay model to an SBML file and return its path."""
    import antimony

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(_DECAY) >= 0, antimony.getLastError()
    name = antimony.getModuleNames()[-1]
    sbml = antimony.getSBMLString(name)
    path = tmp_path / "decay.sbml"
    path.write_text(sbml)
    return str(path)


def test_utc_step_trajectory_real_bridge(tmp_path):
    """AmiciUTCStep runs a full uniform time course from an SBML path."""
    step = AmiciUTCStep(config={"model_id": "test_utc_decay"}, core=allocate_core())
    out = step.update(
        {"model_source": _decay_sbml(tmp_path), "time": 5.0, "n_points": 6}
    )
    res = out["result"]
    assert res["time"][0] == 0.0
    assert abs(res["time"][-1] - 5.0) < 1e-9
    assert len(res["values"]) == 6
    assert "A" in res["columns"]
    ai = res["columns"].index("A")
    # A(t) = 10 * exp(-0.2 t): A(0) = 10, A(5) = 10 * e^-1 ≈ 3.679.
    assert abs(res["values"][0][ai] - 10.0) < 1e-2
    assert abs(res["values"][-1][ai] - 10.0 * math.exp(-1.0)) < 1e-2


def test_steady_state_step_real_bridge(tmp_path):
    """AmiciSteadyStateStep integrates the decay model to its A → 0 steady state."""
    step = AmiciSteadyStateStep(
        config={"model_id": "test_ss_decay"}, core=allocate_core()
    )
    out = step.update({"model_source": _decay_sbml(tmp_path)})
    res = out["result"]
    assert res["kind"] == "steady_state"
    assert res["time"] is None
    assert abs(res["observables"]["A"]) < 1e-3


def test_rejects_no_source():
    proc = AmiciProcess(
        config={"model_id": "test_no_source"},
        core=allocate_core(),
    )
    with pytest.raises(ValueError, match="exactly one of"):
        proc._ensure_compiled()


def test_rejects_multiple_sources():
    proc = AmiciProcess(
        config={
            "antimony": _DECAY,
            "sbml": "<sbml/>",
            "model_id": "test_two_sources",
        },
        core=allocate_core(),
    )
    with pytest.raises(ValueError, match="exactly one of"):
        proc._ensure_compiled()
