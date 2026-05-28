"""Tests for the dashboard-discoverable composite generators."""

from __future__ import annotations

import pytest

amici = pytest.importorskip("amici")
pytest.importorskip("antimony")

from process_bigraph import Composite, allocate_core, gather_emitter_results  # noqa: E402

from pbg_amici import AmiciProcess  # noqa: E402
from pbg_amici.composites.exponential_decay import exponential_decay  # noqa: E402
from pbg_amici.composites.lotka_volterra import lotka_volterra  # noqa: E402
from pbg_amici.composites.mapk_cascade import mapk_cascade  # noqa: E402


def test_generators_are_registered():
    """Decorators must side-effect-register on package import."""
    pytest.importorskip("pbg_superpowers")
    from pbg_superpowers.composite_generator import _REGISTRY

    names = [eid for eid in _REGISTRY if eid.endswith(".amici_exponential_decay")]
    assert names, (
        f"amici_exponential_decay missing from registry; "
        f"have first 5: {list(_REGISTRY)[:5]}"
    )

    for slug in ("amici_lotka_volterra", "amici_mapk_cascade"):
        matches = [eid for eid in _REGISTRY if eid.endswith("." + slug)]
        assert matches, f"{slug} missing"


def test_exponential_decay_runs_in_composite():
    core = allocate_core()
    # `AmiciProcess` is in an installed pbg-* package and discovered by
    # allocate_core() — register_link is unnecessary in production. For
    # safety in case the test runs against a not-yet-discovered core
    # (uvx, isolated venv), register defensively.
    if "AmiciProcess" not in (core.process_registry.list() if hasattr(core, "process_registry") else []):
        core.register_link("AmiciProcess", AmiciProcess)

    doc = exponential_decay(core=core, interval=1.0, k=0.2, A0=10.0)
    sim = Composite({"state": doc}, core=core)
    sim.run(5.0)
    results = gather_emitter_results(sim)
    series = next(iter(results.values()))
    # 5 steps of decay from A0=10 with k=0.2: A(5) ≈ 10*exp(-1) ≈ 3.68
    final_A = series[-1]["states"]["A"]
    assert 3.0 < final_A < 4.5, f"unexpected final A: {final_A}"


def test_lotka_volterra_runs_in_composite():
    core = allocate_core()
    if "AmiciProcess" not in (core.process_registry.list() if hasattr(core, "process_registry") else []):
        core.register_link("AmiciProcess", AmiciProcess)

    doc = lotka_volterra(core=core, interval=0.25)
    sim = Composite({"state": doc}, core=core)
    sim.run(5.0)
    results = gather_emitter_results(sim)
    series = next(iter(results.values()))
    # Just assert the simulation produced changing nonnegative populations.
    prey_vals = [s["states"]["prey"] for s in series]
    pred_vals = [s["states"]["predator"] for s in series]
    assert all(v >= -1e-6 for v in prey_vals)
    assert all(v >= -1e-6 for v in pred_vals)
    assert max(prey_vals) - min(prey_vals) > 0.5, "prey did not vary"
    assert max(pred_vals) - min(pred_vals) > 0.1, "predator did not vary"


def test_mapk_cascade_amplifies_signal():
    core = allocate_core()
    if "AmiciProcess" not in (core.process_registry.list() if hasattr(core, "process_registry") else []):
        core.register_link("AmiciProcess", AmiciProcess)

    doc = mapk_cascade(core=core, interval=1.0, signal=1.0)
    sim = Composite({"state": doc}, core=core)
    sim.run(30.0)
    results = gather_emitter_results(sim)
    series = next(iter(results.values()))
    # K should grow from 0 and reach a meaningful steady-state level.
    K_vals = [s["states"]["K"] for s in series]
    assert K_vals[-1] > 50.0, f"K did not amplify enough: {K_vals[-1]}"
