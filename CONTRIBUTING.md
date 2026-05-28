# Contributing to pbg-amici

## Development setup

`uv` is required. Install with `brew install uv` or `pip install uv`.

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

The first AMICI model compile inside the tests takes ~10 s; the compiled
extension is cached under `amici_models/<amici_version>/<model_id>/`, so
repeated test runs are fast.

## Releasing to PyPI

Tag a commit with `git tag v<VERSION>` and push the tag. The
`.github/workflows/release.yml` workflow publishes to PyPI automatically
using trusted publishing (no tokens needed after initial setup).

PyPI trusted publishing must be configured once per repo. See
<https://docs.pypi.org/trusted-publishers/>.
