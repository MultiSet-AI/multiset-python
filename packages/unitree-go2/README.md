# multiset-unitree-go2

Visual positioning for the Unitree Go2: WebRTC transport, front camera, fisheye
undistortion, and MultiSet VPS localization.

Part of [multiset-python](../../README.md). This package is the Go2 *adapter* —
it owns the transport, the camera, and this robot's measured numbers. The VPS
query, `Pose` and the frame conversions live in
[`multiset-vps`](../vps/README.md) and are shared with every other device.

```python
from multiset.unitree.go2 import Go2

with Go2.from_env() as dog:
    pose = dog.localize()
    if pose:
        print(pose.x, pose.y, pose.yaw_deg, pose.confidence)
```

---

## Seven steps, and where each one lives

| # | step | you call | file |
|---|---|---|---|
| 0 | find the robot's IP *(optional)* | `find_robots()` | `discovery.py` |
| 1 | IP + credentials from `.env` | `Go2Settings.from_env()` | `config.py` |
| 2 | AES key + serial *(once)* | `go2-credentials --save` | `credentials.py` |
| 3 | connect to the robot | `Go2.connect()` | `robot.py` |
| 4 | camera access | *(automatic on connect)* | `robot.py` |
| 5 | capture + undistort | `dog.capture()` | `robot.py` |
| 6 | the VPS query | `dog.localize()` | **`multiset-vps`** |
| 7 | Y-up → Z-up, camera → robot | `dog.base_pose()` | **`multiset-vps`** |

`dog.localize()` does 5 and 6. `dog.base_pose()` does 5, 6 and 7 and hands back
`(x, y, yaw_deg)` for the robot itself.

Seven files in the package, and you only ever open four: `config.py`,
`credentials.py`, `robot.py`, and the example. `discovery.py` is for the one
time you do not know the address; `errors.py` is a lookup; `_webrtc.py` is
private — the asyncio and video-track plumbing, which is not a decision you
make.

### Finding the robot

```python
from multiset.unitree.go2 import find_robots

for host in find_robots():
    print(host)  # 192.168.1.114   go2   ports: 9991
```

This sweeps your subnet for the port only a head unit opens — about five
seconds. It is 254 TCP connects on your own LAN: unremarkable at home, and
capable of tripping intrusion detection on a corporate network.

There is a second method. `credentials.find_serial()` asks over multicast — one
packet, and it returns the serial for free — but the responder does not run on
every firmware. A robot can be powered on, listening on 9991 and perfectly
reachable while answering nothing, which is why it is not on the default path.

A head unit has **9991 open and SSH closed**; the Jetson carrier board is the
reverse and never serves WebRTC. `find_robots` reports both and labels them, so
`GO2_IP` does not end up on the half of the robot that cannot answer.

## Install

On Linux, install PortAudio first. `unitree-webrtc-connect` depends on
`pyaudio`, which publishes no Linux or macOS wheel and compiles against
`portaudio.h` — without it the install fails partway through with a C
compiler error:

```bash
sudo apt-get install -y portaudio19-dev     # Debian/Ubuntu, incl. Jetson
brew install portaudio                      # macOS
```

Both packages, in one command:

```bash
pip install \
  "multiset-vps @ git+https://github.com/MultiSet-AI/multiset-python@vps-v0.1.0#subdirectory=packages/vps" \
  "multiset-unitree-go2 @ git+https://github.com/MultiSet-AI/multiset-python@unitree-go2-v0.1.0#subdirectory=packages/unitree-go2"
```

**Both lines are required.** pip does not follow a git URL to find this
package's `multiset-vps>=0.1,<0.2`, so name it explicitly. Pin tags, never
branches — `@main` gives you different code on every install.

| extra | adds | why it is optional |
|---|---|---|
| *(base)* | transport, camera, undistortion, VPS | 296 MB, 46 packages |
| `[cloud]` | fetching the AES key | needs a TLS-impersonating HTTP client |
| `[viz]` | `examples/visualize.py` only | open3d alone is **284 MB** |

Most of the base footprint is not ours: `opencv-python` is 119 MB and `av`
44 MB, and `unitree-webrtc-connect` pulls in `wasmtime`, `flask-socketio`,
`pyaudio`, `sounddevice` and `lz4`. `[cloud]` arrives with it in practice, so
`go2-credentials` usually works without asking for the extra — declare it
anyway if you rely on it.

## Set it up once

```bash
cp ../../.env.example .env       # then set GO2_IP and the three MULTISET_* values
go2-credentials --email you@example.com --save   # step 2: writes GO2_SN + GO2_AES_KEY
python examples/quickstart.py
```

The three `MULTISET_*` values come from the
[Developer Platform](https://developer.multiset.ai) — sign up, create a map for
its map code, copy your client ID and secret. `GO2_IP` is the one thing you must
supply yourself. Nothing is read at import
time — `.env` is a convenience, and every value can be passed explicitly:

```python
from multiset.unitree.go2 import Go2, Go2Settings
from multiset.vps import VPSSettings

dog = Go2(
    Go2Settings(robot_ip="192.168.1.114", aes_key="…"),
    VPSSettings(client_id="…", client_secret="…", map_code="MAP_…"),
)
```

Two settings objects because they are two different things with two different
owners: the robot's address and key belong to the robot in front of you, the
MultiSet credentials belong to your account and are the same for every device.
`Go2.from_env()` builds both.

## The thing that will cost you an afternoon

**A Go2 with a Jetson carrier board puts _two_ computers on your wifi**, and
only one speaks WebRTC:

| role | ports | this is… |
|---|---|---|
| **GO2 head unit** | **`9991` only** | the WebRTC endpoint — **this is `GO2_IP`** |
| Jetson board | `22`, `80`, `111`, `4000` | SSH + the `unitree-upgrade` page. Never serves WebRTC |

Both are genuine Unitree hardware, so finding the Jetson feels like finding the
robot. Point `GO2_IP` at it and you get `SignallingUnavailable`, which reads
exactly like a dead robot. The head unit also opens `9991` late in its boot, so
a robot that just powered on can fail this way for a minute and then be fine.

## Step 2: the AES key

Firmware ≥ 1.1.15 encrypts the LAN handshake and refuses the connection without
a per-device key. That key **cannot be derived, guessed, or read from the
robot's IP** — `con_notify` only tells you a key is *required*, because its
reply is already encrypted under it. The only source is the Unitree cloud
account the robot is bound to:

```bash
go2-credentials --email you@example.com --save
```

In Python, if you would rather not shell out:

```python
from multiset.unitree.go2 import fetch_credentials, save_to_env

creds = fetch_credentials("you@example.com", password)
save_to_env(creds[0])
```

## Frames — read this before trusting a pose

The conversions live in `multiset.vps` because they are not Go2-specific; this
robot's *numbers* live here (`GO2_FRONT_720P`, `GO2_MOUNT`). Each is silent when
wrong — you get a plausible result, not an error:

- **VPS returns Y-up.** Odometry and maps are Z-up. `YUP_TO_ZUP` handles it, in
  one place.
- **A VPS pose describes the _camera_.** `camera_pose_to_base()` applies this
  robot's mount chain. Measured on hardware, the two differ by **0.300 m and
  about 90° of heading**.
- **Raw and rectified intrinsics are not interchangeable.** Raw fx ≈ 797
  describes the fisheye sensor; rectified fx ≈ 728 describes the undistorted
  image. Sending the raw set with a rectified image is a ~10% error on every
  bearing — and VPS still answers `poseFound: true`.

`FRONT.undistort()` returns the image and its intrinsics **as a pair** so they
cannot drift apart. See [docs/frames.md](../../docs/frames.md).

## Errors

Everything inherits from `Go2Error`, which inherits from
`multiset.vps.MultisetError`. The library never calls `sys.exit()`.

```python
from multiset.unitree.go2 import Go2, Go2Error, SignallingUnavailable

try:
    with Go2.from_env() as dog:
        pose = dog.localize()
except SignallingUnavailable:
    ...  # wrong address, or the robot is still booting
except Go2Error:
    ...  # anything else
```

`CameraError`, `FrameTimeout` and `CalibrationError` are defined in
`multiset.vps` and re-exported here. They are the *same* classes, so
`except FrameTimeout` works whichever import you used.

**`poseFound=false` is not an error.** A featureless wall legitimately fails to
match, so `localize()` returns a `Pose` with `found=False` rather than raising.
Check `if pose:`.

## Threading

The transport runs an asyncio loop on a background thread.

- `connect()`, `localize()` and `capture()` **block** on your thread.
- Odometry and camera callbacks **run on the loop thread**. Blocking in one
  stalls the heartbeat, the video track and every other topic — copy the value
  out and return.
- `Go2` is not safe to share across threads without your own locking.

## Examples

| file | |
|---|---|
| [`examples/quickstart.py`](examples/quickstart.py) | connect, localize, print a pose |
| [`examples/localize_loop.py`](examples/localize_loop.py) | hold the link open and localize repeatedly |
| [`examples/visualize.py`](examples/visualize.py) | all seven steps, ending in a 3D view *(needs `[viz]`)* |

## Development

```bash
uv sync --all-extras
uv run pytest packages/unitree-go2
```

Releases are cut by tag prefix — `unitree-go2-v0.2.1` publishes only this
package. See [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
