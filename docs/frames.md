# Frames and conventions

Three conversions decide whether a pose means anything. Each is **silent when
wrong**: you get a plausible number rather than an error, and the mistake only
shows up as a robot that drives into a wall.

---

## 1. VPS is Y-up. Everything else is Z-up.

MultiSet returns poses in a right-handed **Y-up** frame, and the textured map
mesh is exported in that same frame. Odometry, costmaps and the viewer are
**Z-up**.

```
YUP_TO_ZUP:  (x, y, z) -> (x, -z, y)
```

Both the pose and the mesh get it applied, in exactly one place
(`multiset.vps.YUP_TO_ZUP`). Convert one and not the other and everything
still renders — the robot is simply standing in a different room from the one
the map is showing.

## 2. A VPS pose describes the camera, not the robot

The pose you get back is the **camera's**. `base_link` is 0.30 m behind it along
the mount chain, and the camera frame is ARKit-style (+Y up, −Z forward) where
the Go2's mount chain is OpenCV optical (+Y down, +Z forward).

```python
from multiset.unitree.go2.dimos import camera_pose_to_base
T_base = camera_pose_to_base(pose.matrix)
```

Measured on real hardware, camera versus `base_link`:

| | position | yaw |
|---|---|---|
| camera | `(+2.431, +0.783)` | `+100.0°` |
| base_link | `(+2.726, +0.835)` | `−169.9°` |

**0.300 m apart** — matching the mount chain exactly — and **about 90° apart in
heading**. Draw the camera pose and the robot appears a body-length ahead of
itself, facing the wrong way, in a picture that looks completely reasonable.

## 3. Raw and rectified intrinsics are not interchangeable

The front camera is an equidistant fisheye. There are two sets of numbers:

| | fx | describes | sent to VPS? |
|---|---|---|---|
| **raw fisheye** | ~797.48 | the distorted sensor image | **never** |
| **rectified pinhole** | ~728.47 | the undistorted image | **yes** |

The rectified focal length is shorter because `balance=0.0` crops to pixels
backed by real source data. Send the raw set with a rectified image and every
bearing is off by ~10% — and the server still answers `poseFound: true`.

This is why `undistort()` returns **both together**:

```python
image, K = undistort(frame)      # they cannot drift apart
pose = client.localize(image, K)
```

## 4. Odometry is in the robot's own frame

Odometry starts wherever the robot booted. It has no relationship to the map
until you anchor it to a VPS fix:

```python
from multiset.unitree.go2.dimos import compose_map_from_odom
x, y, yaw = compose_map_from_odom(anchor_map, anchor_odom, odom_now)
```

`anchor_map` is the map pose at the last fix, `anchor_odom` the odometry reading
at that same moment. The gap between the composed track and the *next* fix is
exactly the drift that re-anchor had to correct — which is why drawing both is
worth doing.

One wrinkle when replaying recorded runs: fixes are stamped with wall-clock time
while odometry counts seconds from start, so the two **cannot be matched by
timestamp**. Match by position instead.

## 5. Standing height

A pose is `(x, y, yaw)` on the floor plane. `base_link` sits ~0.32 m above the
feet, so the viewer lifts the model by `stand_height()`. Skip it and the robot
renders buried to its belly in the floor.
