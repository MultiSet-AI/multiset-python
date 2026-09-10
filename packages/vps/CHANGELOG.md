# Changelog — multiset-vps

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this package adheres to [Semantic Versioning](https://semver.org/).

Versions are independent of the other packages in this repo. Releases are cut by
tag prefix: `vps-v0.1.0`.

While on `0.x`, minor versions may contain breaking changes. The API will be
frozen at `1.0.0`.

## [Unreleased]

### Added

- 360 camera support. `localize_panorama()` sends a 2:1 equirectangular frame as
  an `imageType=equirect` query, which carries **no intrinsics** — the
  projection is described by the image's own shape, so there is nothing to
  calibrate. Verified against the API.
- `Panorama` and `PanoramaSource` — the equirect counterparts of `Frame` and
  `FrameSource`. `localize()` now takes either: a source with
  `capture_panorama()` is sent as equirect, one with `capture()` as pinhole.
- `pose_to_hint()` — turns a fix into the next query's `hint_position`. Not a
  no-op: a pose comes back right-handed while the hint is read in the map's
  left-handed frame, so X flips.
- `encode_equirect()`, `MAX_EQUIRECT_WIDTH`, `EQUIRECT_JPEG_BUDGET`. Equirect
  queries are **not** subject to the 1280 px pinhole cap — the service accepts
  up to 4096x2048, and a panorama shrunk to 1280x640 loses what the solver
  needs.
- `attempts=` on the panorama query retries a 5xx, which is how the service
  reports a query instance still waking from idle. The first fix after a long
  pause can take a couple of minutes.
- `VPSError.status` carries the HTTP status, so a caller can tell a 5xx worth
  retrying from a 400 that never will be.

## [0.1.0] - 2026-08-26

Initial release.
