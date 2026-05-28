"""Single-species first-order decay — the smoke-test composite."""

from ._decorator import composite_generator


_ANTIMONY = """
model exponential_decay
  A = 10
  A' = -k * A
  k = 0.2
end
"""


@composite_generator(
    name="amici_exponential_decay",
    description=(
        "Single-species exponential decay simulated by AMICI (CVODES). "
        "Smoke-test composite — verifies the AMICI bridge can compile, "
        "integrate, and emit observables for a one-state ODE."
    ),
    parameters={
        "interval": {
            "type": "float",
            "default": 1.0,
            "description": "Per-step integration window (time units)",
        },
        "k": {
            "type": "float",
            "default": 0.2,
            "description": "First-order decay rate constant",
        },
        "A0": {
            "type": "float",
            "default": 10.0,
            "description": "Initial concentration of species A",
        },
    },
)
def exponential_decay(core=None, *, interval=1.0, k=0.2, A0=10.0):
    return {
        "amici": {
            "_type": "process",
            "address": "local:AmiciProcess",
            "config": {
                "antimony": _ANTIMONY,
                "model_id": "exp_decay",
            },
            "interval": float(interval),
            "inputs": {
                "states": ["stores", "states"],
                "parameters": ["stores", "parameters"],
                "fixed_parameters": ["stores", "fixed_parameters"],
            },
            "outputs": {
                "states": ["stores", "states"],
                "observables": ["stores", "observables"],
            },
        },
        "stores": {
            "states": {"A": float(A0)},
            "parameters": {"k": float(k)},
            "fixed_parameters": {},
            "observables": {},
        },
        "emitter": {
            "_type": "step",
            "address": "local:RAMEmitter",
            "config": {
                "emit": {
                    "states": "map[string,float]",
                    "observables": "map[string,float]",
                    "time": "float",
                },
            },
            "inputs": {
                "states": ["stores", "states"],
                "observables": ["stores", "observables"],
                "time": ["global_time"],
            },
        },
    }
