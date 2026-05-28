"""Lotka-Volterra predator-prey ODE simulated by AMICI."""

from ._decorator import composite_generator


_ANTIMONY = """
model lotka_volterra
  // species
  prey = 10
  predator = 5

  // rate parameters (avoid antimony's reserved names: delta, gamma)
  alpha    = 1.1   // prey birth rate
  beta     = 0.4   // predation rate
  d_gain   = 0.1   // predator growth per prey eaten
  d_death  = 0.4   // predator death rate

  // observables (derived signals)
  ratio_pp := predator / (prey + 1e-9)
  totalpop := prey + predator

  // dynamics
  prey'     =  alpha  * prey                  - beta    * prey * predator
  predator' =  d_gain * prey * predator       - d_death * predator
end
"""


@composite_generator(
    name="amici_lotka_volterra",
    description=(
        "Classical Lotka-Volterra predator-prey ODE solved by AMICI "
        "(CVODES). Demonstrates two coupled nonlinear species and "
        "observable expressions (ratio, total)."
    ),
    parameters={
        "interval": {
            "type": "float",
            "default": 0.5,
            "description": "Per-step integration window (time units)",
        },
        "alpha": {
            "type": "float",
            "default": 1.1,
            "description": "Prey birth rate",
        },
        "beta": {
            "type": "float",
            "default": 0.4,
            "description": "Predation rate",
        },
        "d_gain": {
            "type": "float",
            "default": 0.1,
            "description": "Predator growth per prey eaten",
        },
        "d_death": {
            "type": "float",
            "default": 0.4,
            "description": "Predator death rate",
        },
        "prey0": {
            "type": "float",
            "default": 10.0,
            "description": "Initial prey population",
        },
        "predator0": {
            "type": "float",
            "default": 5.0,
            "description": "Initial predator population",
        },
    },
)
def lotka_volterra(
    core=None,
    *,
    interval=0.5,
    alpha=1.1,
    beta=0.4,
    d_gain=0.1,
    d_death=0.4,
    prey0=10.0,
    predator0=5.0,
):
    return {
        "amici": {
            "_type": "process",
            "address": "local:AmiciProcess",
            "config": {
                "antimony": _ANTIMONY,
                "model_id": "lotka_volterra",
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
            "states": {
                "prey": float(prey0),
                "predator": float(predator0),
            },
            "parameters": {
                "alpha": float(alpha),
                "beta": float(beta),
                "d_gain": float(d_gain),
                "d_death": float(d_death),
            },
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
