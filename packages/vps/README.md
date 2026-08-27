# multiset-vps

MultiSet visual positioning, independent of what took the picture. A rectified
frame and the intrinsics describing it go in; a `Pose` comes out.

Standalone: it needs no camera, no device and no hardware. Anything that can
produce a rectified image and its intrinsics can be localized.

```python
from multiset.vps import PinholeIntrinsics, localize_image
import cv2

image = cv2.imread("rectified.png")
K = PinholeIntrinsics(fx=728.47, fy=727.57, px=646.64, py=346.46, width=1280, height=720)

pose = localize_image(image, K)
if pose:
    print(pose.x, pose.y, pose.yaw_deg, pose.confidence)
```

---

## Install

```bash
pip install "multiset-vps @ git+https://github.com/MultiSet-AI/multiset-python@vps-v0.1.0#subdirectory=packages/vps"
```

Three dependencies — numpy, opencv-python, requests.

## Configure

Get the three values from the [MultiSet Developer Platform](https://developer.multiset.ai):
sign up, create a map for its **map code**, then copy your **client ID** and
**client secret**. API reference at [docs.multiset.ai](https://docs.multiset.ai).

Copy [`.env.example`](../../.env.example) to `.env` and fill in the MultiSet
section: `MULTISET_CLIENT_ID`, `MULTISET_CLIENT_SECRET`, `MULTISET_MAP_CODE`.

Nothing is read at import time. `.env` is a convenience — every value can be
passed explicitly instead, and explicit always wins:

```python
from multiset.vps import VPSSettings, VPSClient

client = VPSClient(VPSSettings(client_id="…", client_secret="…", map_code="MAP_…"))
```

These credentials belong to your MultiSet **account**, not to any one device,
which is why they live here rather than in a device's settings object. A
capture-only script should not have to supply a map code it never uses.

## Two ways in

**You have a frame already** — a video file, a dataset on disk, an upload:

```python
from multiset.vps import localize_image

pose = localize_image(image, intrinsics)
```

**You have a device** — anything satisfying the `FrameSource` protocol:

```python
from multiset.vps import localize

pose = localize(source)  # source.capture() -> Frame
```

`FrameSource` is one method:

```python
class FrameSource(Protocol):
    def capture(self) -> Frame: ...  # Frame = (image, intrinsics)
```

That is the entire contract. In a
loop, build the client once and pass it — it holds the cached auth token, and a
fresh client per query is a token request per query:

```python
client = VPSClient()
while True:
    pose = localize(source, client=client)
```

## Frames — read this before trusting a pose

Three conversions that are silent when wrong. Getting one backwards produces a
plausible-looking result rather than an error, which is why each has exactly one
implementation and it lives here:

- **VPS returns Y-up.** Odometry, costmaps and viewers are Z-up. `YUP_TO_ZUP`
  handles it.
- **VPS returns an ARKit-style camera frame** (+Y up, −Z forward); mount chains
  are written in OpenCV optical (+Y down, +Z forward). `CAM_TO_OPTICAL`.
- **A VPS pose describes the *camera*, not the thing carrying it.** Give
  `camera_pose_to_origin()` the device's `Mount` and it returns the carrier's
  pose. On a typical mount the two differ by **tens of centimetres and often 90° of
  heading** — and the wrong one looks perfectly plausible in a screenshot.

Plus the one that is not a frame conversion but fails the same way:

- **Raw and rectified intrinsics are not interchangeable.** A fisheye
  calibration describes the *sensor*; a `PinholeIntrinsics` describes the image
  after remapping — commonly a ~10% difference.
  bearing — and VPS still answers `poseFound: true`.

`Rectifier.undistort()` returns the image and its intrinsics **as a pair**, and
nothing in this package accepts one without the other. See
[docs/frames.md](../../docs/frames.md).

## Rectification

The machinery is here; the numbers live in the device packages, next to the
hardware they describe.

```python
from multiset.vps import FisheyeCalibration, Rectifier

calib = FisheyeCalibration(
    name="my-lens-1280x720",
    fx=797.47,
    fy=796.48,
    cx=643.53,
    cy=349.27,
    k=(-0.0731, -0.0234, -0.0069, 0.0092),
    width=1280,
    height=720,
)
rect = Rectifier(calib)  # remap tables built once, cached
image, K = rect.undistort(raw)
```

The resolution is part of the calibration on purpose: these coefficients
describe one sensor at one readout, and applying them to a resized frame yields
a plausible picture with wrong geometry. `undistort()` raises
`CalibrationError` rather than letting that through.

## Errors

`MultisetError` is the root for **every** package in the family, so one except
clause covers this package and every device alongside it.

```
MultisetError
├─ ConfigError         # no credentials, no map code
├─ CalibrationError    # frame does not match its calibration
├─ CameraError         # a frame source produced nothing
│  └─ FrameTimeout
└─ VPSError
   └─ VPSAuthError     # check MULTISET_CLIENT_ID / _SECRET
```

The library never calls `sys.exit()`.

**`poseFound=false` is not an error.** A featureless wall legitimately fails to
match, so a query returns a `Pose` with `found=False` rather than raising. Check
`if pose:`.

## Examples

| file | |
|---|---|
| [`examples/01_localize_a_file.py`](examples/01_localize_a_file.py) | no device at all — localize an image on disk |

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
