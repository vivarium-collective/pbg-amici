"""Optional ``@composite_generator`` shim.

When ``pbg_superpowers`` is installed (the vivarium-dashboard runtime), the
real decorator registers each generator with the dashboard's discovery
machinery. When it isn't, we fall back to a no-op so the module still
imports and the decorated functions remain directly callable.
"""

from __future__ import annotations

try:  # pragma: no cover — exercised by both branches in tests + dashboard
    from pbg_superpowers.composite_generator import composite_generator
except Exception:  # ImportError or unrelated failure inside that package

    def composite_generator(*_args, **_kwargs):  # type: ignore[no-redef]
        def _wrap(fn):
            return fn

        return _wrap


__all__ = ["composite_generator"]
