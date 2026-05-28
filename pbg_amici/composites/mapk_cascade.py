"""Minimal three-tier MAPK signaling cascade simulated by AMICI.

Simplified Goldbeter-Koshland-style cascade: an input signal activates a
MAPKKK kinase, which activates MAPKK, which activates MAPK. Each level has
an explicit deactivation phosphatase. Demonstrates a longer, biologically
flavored model than the textbook smoke tests.
"""

from ._decorator import composite_generator


_ANTIMONY = """
model mapk_cascade
  // active forms
  KKK = 0.0
  KK  = 0.0
  K   = 0.0

  // total pool (conservation: KKK + KKK_inact = KKK_total)
  KKK_total = 100.0
  KK_total  = 200.0
  K_total   = 300.0

  // input signal — drives KKK activation
  signal = 1.0

  // activation rate constants
  k1 = 0.05  // signal -> KKK
  k2 = 0.15  // KKK -> KK
  k3 = 0.15  // KK  -> K
  // deactivation rate constants
  d1 = 0.10
  d2 = 0.20
  d3 = 0.25

  // dynamics
  KKK' = k1 * signal * (KKK_total - KKK) - d1 * KKK
  KK'  = k2 * KKK    * (KK_total  - KK)  - d2 * KK
  K'   = k3 * KK     * (K_total   - K)   - d3 * K

  // observables (downstream signal strength + amplification ratio)
  downstream := K
  amplification := (K + 1e-9) / (signal + 1e-9)
end
"""


@composite_generator(
    name="amici_mapk_cascade",
    description=(
        "Three-tier MAPK signaling cascade (KKK→KK→K) with explicit "
        "phosphatases, simulated by AMICI (CVODES). Demonstrates a "
        "biologically flavored multi-species model and observable expressions."
    ),
    parameters={
        "interval": {
            "type": "float",
            "default": 0.5,
            "description": "Per-step integration window (time units)",
        },
        "signal": {
            "type": "float",
            "default": 1.0,
            "description": "Input signal driving KKK activation",
        },
        "k1": {
            "type": "float",
            "default": 0.05,
            "description": "Activation rate: signal -> KKK",
        },
        "k2": {
            "type": "float",
            "default": 0.15,
            "description": "Activation rate: KKK -> KK",
        },
        "k3": {
            "type": "float",
            "default": 0.15,
            "description": "Activation rate: KK -> K",
        },
    },
)
def mapk_cascade(
    core=None, *, interval=0.5, signal=1.0, k1=0.05, k2=0.15, k3=0.15
):
    return {
        "amici": {
            "_type": "process",
            "address": "local:AmiciProcess",
            "config": {
                "antimony": _ANTIMONY,
                "model_id": "mapk_cascade",
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
            "states": {"KKK": 0.0, "KK": 0.0, "K": 0.0},
            "parameters": {
                "signal": float(signal),
                "k1": float(k1),
                "k2": float(k2),
                "k3": float(k3),
                "d1": 0.10,
                "d2": 0.20,
                "d3": 0.25,
                "KKK_total": 100.0,
                "KK_total": 200.0,
                "K_total": 300.0,
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
