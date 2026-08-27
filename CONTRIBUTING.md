# Contributing

## Setup

```bash
sudo apt-get install -y portaudio19-dev   # or: brew install portaudio
git clone https://github.com/MultiSet-AI/multiset-python
cd multiset-python
uv sync --all-extras
uv run pytest
```

PortAudio is not optional: `unitree-webrtc-connect` pulls `pyaudio`, which has
no Linux or macOS wheel and builds from source. CI installs it too.

`uv sync` installs every package in `packages/` editable into one venv. Each
adapter's `[tool.uv.sources]` points `multiset-vps` at `packages/vps` in your
working tree, so a change to the core is live everywhere immediately. uv strips
it from the built wheel, which keeps the plain `multiset-vps>=0.1,<0.2`.

Prove the namespace resolves before anything else. It is the failure that looks
like nothing else:

```bash
uv run python -c "import multiset.vps, multiset.unitree.go2.dimos; print('ok')"
```

## Before you open a PR

```bash
uv run ruff check packages tests && uv run ruff format packages tests
uv run mypy
uv run pytest
```

CI runs all of it on Python 3.10–3.12.

## The namespace rule

`src/multiset/`, `src/multiset/unitree/` and `src/multiset/unitree/go2/` are
PEP 420 namespace directories, shared across distributions.

> **Never create an `__init__.py` in any of them.**

One `__init__.py` turns the namespace into a regular package owned by whichever
distribution shipped it, and every *sibling* `multiset.*` package becomes
invisible — `import multiset.vps` succeeds, `import multiset.unitree.go2.dimos`
raises `ModuleNotFoundError`, and nothing in the traceback points at the cause.
A CI job and `packages/vps/tests/test_namespace.py` both guard it. Leave them
alone.

## Where new code goes

**Anything a second device would also need belongs in `multiset.vps`.**

Core owns the maths — the VPS protocol, `Pose`, frame conversions,
rectification, the error hierarchy. Adapters own the measurements and the
transport — fisheye coefficients, mount chains, handshakes, discovery.

The test: if the code would be copy-pasted verbatim into the next adapter, it is
in the wrong package. Moving a file between packages is a `git mv` and a PR here;
in separate repos it would be two releases and a version bump.

Never import an adapter from the core. `multiset.vps` must not know that
`multiset.unitree.go2.dimos` exists.

## The layering rule

Each package's library modules **raise exceptions and return values**. `cli/`
catches them, prints, prompts and sets exit codes.

If a function both computes and prints, it is in the wrong layer. This is not
style: the library gets imported into services where stdout is a log stream and
a stray `input()` is a hang.

## Tests

Everything in `packages/*/tests/` runs with **no robot, no credentials and no
internet**. That is a deliberate constraint: a suite that needs hardware is a
suite nobody runs.

Tests live with the package they test. A test that needs an optional extra skips
rather than fails:

```python
pytest.importorskip("open3d", reason="needs the [viz] extra")
```

Anything that genuinely needs hardware goes behind a marker and stays out of CI:

```python
@pytest.mark.hardware
def test_against_a_real_go2():
    ...
```

Run those deliberately with `uv run pytest -m hardware`.

Test files use `--import-mode=importlib` (set in the root `pyproject.toml`)
because two packages can both have a `tests/test_settings.py`.

## Secrets

Never commit `.env`, a `GO2_AES_KEY`, a MultiSet client secret, or a robot
serial. Don't paste them into issues either — every settings object has a
`redacted()` that masks secrets to lengths; use it when attaching output to a bug
report.

## Third-party assets

The Unitree Go2 model is **downloaded on demand, never vendored** (see NOTICE).
CI fails the build if `.dae`, `.stl` or `.urdf` files appear in a wheel. Please
don't "optimise" that by checking them in.

## Commits and releases

- Conventional-ish commit subjects (`fix:`, `feat:`, `docs:`) — readable history
  matters more than strict tooling. Scope them by package where it helps:
  `fix(vps): …`.
- Add your entry under `## [Unreleased]` in that package's `CHANGELOG.md` in the
  same PR.
- Releases are SemVer per package, tagged `<package>-v<X.Y.Z>`:
  `vps-v0.1.1`, `unitree-go2-dimos-v0.2.0`. The tag prefix is what routes the
  release workflow, and `hatch-vcs` reads the version from it — there is no
  hand-edited version constant anywhere.
- While on `0.x`, minor versions may break the API. Say so in the changelog.
