# Changelog — multiset-insta360

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this package adheres to [Semantic Versioning](https://semver.org/).

Versions are independent of the other packages in this repo. Releases are cut by
tag prefix: `insta360-v0.1.0`.

While on `0.x`, minor versions may contain breaking changes. The API will be
frozen at `1.0.0`.

## [Unreleased]

### Added

- First release. Visual positioning from an Insta360 X-series camera in webcam
  mode, where it is a plain UVC device already delivering stitched 2:1
  equirectangular frames — so there is no Insta360 SDK here, and nothing to
  calibrate.
- `UsbCamera` — the camera on this machine's USB. Works with the X3, X4 and X5:
  what it needs is a UVC device whose frames are 2:1, not a particular model.
  Refuses anything else with `NotPanoramic` rather than uploading a frame that
  cannot localize.
- `SSHCamera` — the same camera plugged into a robot, read over SSH. Nothing is
  installed on the robot: it needs only its stock `sshd` and the ffmpeg or
  GStreamer its image already ships, and the session itself carries the video.
  Four pipelines are tried in order so the robot needs no setup.
- Both satisfy `multiset.vps.PanoramaSource`, so moving from a laptop to a robot
  changes one line and nothing downstream.
- `Localizer` — a loop that chains the search hints, waits out a cold start, and
  reuses one client. A lost pose drops the hint, because a stale one pins the
  search where the camera no longer is.
- `Insta360Settings` / `SSHCamera.from_env()` — `INSTA360_SSH_HOST` and
  `INSTA360_DEVICE`, with the same precedence as every other package.
- Requires `multiset-vps>=0.1.1` for the equirect query.
