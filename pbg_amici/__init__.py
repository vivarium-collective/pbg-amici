"""pbg-amici: process-bigraph wrapper for AMICI."""

from .processes import AmiciProcess
from . import composites  # noqa: F401  (registers @composite_generator decorations)

__all__ = ["AmiciProcess"]
