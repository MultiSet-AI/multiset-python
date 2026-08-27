<a href="https://multiset.ai"><img src="docs/img/multiset-logo.png" alt="MultiSet" height="56"></a>

# multiset-python

MultiSet visual positioning for Python. One repo, several packages: a
device-agnostic VPS core, and one adapter per robot or camera.

[Developer Platform](https://developer.multiset.ai) ·
[Docs](https://docs.multiset.ai) ·
[multiset.ai](https://multiset.ai)

| package | `import` | what it owns |
|---|---|---|
| [`multiset-vps`](packages/vps/) | `multiset.vps` | VPS client, `Pose`, frame conventions, rectification |
| [`multiset-unitree-go2`](packages/unitree-go2/) | `multiset.unitree.go2` | WebRTC transport, front camera, discovery, Go2 calibration |

One mapping rule, no exceptions: **every hyphen after `multiset` becomes a
dot.** `multiset-unitree-go2` → `multiset.unitree.go2`.

```python
from multiset.unitree.go2 import Go2
from multiset.vps import localize

with Go2.from_env() as dog:
    pose = localize(dog)                 # the same call for every device
    if pose:
        print(pose.x, pose.y, pose.yaw_deg, pose.confidence)
```

---

## Install

Both packages, in one command:

```bash
pip install \
  "multiset-vps @ git+https://github.com/MultiSet-AI/multiset-python@vps-v0.1.0#subdirectory=packages/vps" \
  "multiset-unitree-go2 @ git+https://github.com/MultiSet-AI/multiset-python@unitree-go2-v0.1.0#subdirectory=packages/unitree-go2"
```

Both lines are required: pip does not follow a git URL to find the core, so the
adapter's `multiset-vps>=0.1,<0.2` has to be named explicitly.

The Go2 adapter needs PortAudio present first (`apt install portaudio19-dev`,
or `brew install portaudio`): it depends on `pyaudio`, which has no Linux or
macOS wheel. `multiset-vps` alone needs nothing.

Only need poses from frames you already have? `multiset-vps` stands alone: three
dependencies, no robot, no renderer.

## Getting credentials

You need a MultiSet account and a map before any of this returns a pose.

1. Sign up at the [Developer Platform](https://developer.multiset.ai)
2. Create a map — you get a **map code** like `MAP_XXXXXXXXXX`
3. Copy your **client ID** and **client secret**

Put all three in `.env` (see [.env.example](.env.example)):

```bash
MULTISET_CLIENT_ID=...
MULTISET_CLIENT_SECRET=...
MULTISET_MAP_CODE=MAP_XXXXXXXXXX
```

API reference: [docs.multiset.ai](https://docs.multiset.ai).

## The core / adapter split

The VPS half of this is not robot-specific: the API client, the pose type, the
Y-up→Z-up conversion, the raw-vs-rectified intrinsics distinction. The transport
half is entirely device-specific. So the family is **one core plus N adapters**,
not N independent SDKs.

The contract between them is one method:

```python
class FrameSource(Protocol):
    def capture(self) -> Frame: ...      # Frame = (rectified image, intrinsics)
```

Everything device-agnostic — `localize()`, `Pose`, `Mount`, `Rectifier` — is
written against that, which is why adding a camera costs nothing in the core.
The rule for where new code goes: **anything a second device would also need
belongs in `multiset.vps`.** Core owns the maths, adapters own the measurements.

## Layout

```
multiset-python
├─ pyproject.toml            uv workspace + lint/type/test config
├─ packages/                 one directory per distribution, each with examples/
│  ├─ vps/                   multiset-vps
│  └─ unitree-go2/     multiset-unitree-go2
├─ docs/frames.md            the conversions that are silent when wrong
└─ .github/workflows/  ci.yml · release.yml
```

`src/multiset/` and `src/multiset/unitree/` are PEP 420 namespace directories.
**Neither may ever contain an `__init__.py`** — one does, and every sibling
`multiset.*` distribution becomes
unimportable with a `ModuleNotFoundError` that points nowhere near the cause. CI
and a unit test both guard it.

## Development

```bash
git clone https://github.com/MultiSet-AI/multiset-python
cd multiset-python
uv sync --all-extras                          # every package editable, one venv
uv run python -c "import multiset.vps, multiset.unitree.go2; print('ok')"
uv run pytest
```

Python 3.10–3.12 is what CI runs. Newer works too, minus the `viz` extra:
open3d has no wheel past 3.12, so `--all-extras` resolves without the viewer.

Editing `packages/vps/src/multiset/vps/frames.py` is live in the adapter
immediately — no version bump, no reinstall. That is the property a monorepo buys
and separate repos charge for.

## Versioning and releases

Each package versions independently. Releases are driven entirely by **tag
prefix**:

```bash
git tag unitree-go2-v0.2.1 && git push --tags   # publishes only that package
git tag vps-v0.1.1 && git push --tags                 # publishes only the core
```

`hatch-vcs` derives the version from that tag with a `--match` per package, so
one package can never pick up another's version. `release.yml` builds, verifies
the wheel version equals the tag, and attaches artifacts. The
`PUBLISH_TO_PYPI` repository variable controls trusted publishing.

Adapters pin the core on a compatible range (`multiset-vps>=0.1,<0.2`), never a
`git+` URL: a direct reference in `[project.dependencies]` cannot be uploaded.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The Unitree Go2 3D model is **not** redistributed — the viz extra downloads it
on demand into a local cache. CI fails the build if it ever appears in a wheel.
