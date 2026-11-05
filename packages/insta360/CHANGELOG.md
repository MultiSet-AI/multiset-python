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
- `UsbCamera` — a 360 camera on this machine's USB. Tested on the X5; what it
  needs is a UVC device whose frames are 2:1, not a particular model. Refuses
  anything else with `NotPanoramic` rather than uploading a frame that cannot
  localize.
- `UsbCamera` satisfies `multiset.vps.PanoramaSource`, so `localize(cam)` sends
  it as an equirect query.
- `Localizer` — a loop that chains the search hints, waits out a cold start, and
  reuses one client. A lost pose drops the hint, because a stale one pins the
  search where the camera no longer is.
- Requires `multiset-vps>=0.1.1` for the equirect query.
