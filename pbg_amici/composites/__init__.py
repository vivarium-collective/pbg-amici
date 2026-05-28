"""Dashboard-discoverable composite generators for pbg-amici."""

from . import exponential_decay  # noqa: F401
from . import lotka_volterra  # noqa: F401
from . import mapk_cascade  # noqa: F401

from .exponential_decay import exponential_decay as exponential_decay_gen
from .lotka_volterra import lotka_volterra as lotka_volterra_gen
from .mapk_cascade import mapk_cascade as mapk_cascade_gen

__all__ = ["exponential_decay_gen", "lotka_volterra_gen", "mapk_cascade_gen"]
