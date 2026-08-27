"""Private: the WebRTC link and the video track. Import `Go2` instead.

The transport underneath is asyncio on a background thread; everything above is
blocking. Two rules follow:

1. Nothing touches the data channel from your thread -- aiortc's `send` is not
   thread-safe, so publishes and subscribes are bounced onto the loop.
2. Subscription and camera callbacks RUN on the loop thread. Blocking in one
   stalls the heartbeat and every other topic. Copy the value out and return.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np
from multiset.vps import FrameTimeout
from unitree_webrtc_connect.constants import (
    DATA_CHANNEL_TYPE,
    RTC_TOPIC,
    SPORT_CMD,
    WebRTCConnectionMethod,
)
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection

from .config import Go2Settings
from .errors import AuthenticationError, ConnectionFailed, SignallingUnavailable

log = logging.getLogger(__name__)


# Never changed unless asked: switching the controller under a standing robot
# is a real-world side effect, not a connection detail.
MOTION_MODES = ("normal", "ai", "advanced", "mcf")

_JOIN_TIMEOUT = 5.0


class Go2Transport:
    """Owns the event loop thread and the WebRTC session."""

    def __init__(
        self,
        settings: Go2Settings | None = None,
        *,
        method: WebRTCConnectionMethod = WebRTCConnectionMethod.LocalSTA,
        disable_traffic_saving: bool = True,
        lidar_decoder: str | None = None,
        motion_mode: str | None = None,
    ) -> None:
        self.settings = settings or Go2Settings.from_env()
        self.ip = self.settings.require_robot()
        # "" means "this firmware predates encryption, send no key".
        self.aes_key = self.settings.aes_key or None
        self.method = method
        self.disable_traffic_saving = disable_traffic_saving
        self.lidar_decoder = lidar_decoder
        self.motion_mode = motion_mode
        if motion_mode is not None and motion_mode not in MOTION_MODES:
            raise ValueError(f"motion_mode must be one of {MOTION_MODES}, got {motion_mode!r}")

        self.conn: UnitreeWebRTCConnection | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._connected = False
        # The transport keeps ONE callback per topic, so a second subscriber
        # would evict the first. One dispatcher, fanned out here.
        self._callbacks: dict[str, list[Callable[[dict], None]]] = {}
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected and bool(getattr(self.conn, "isConnected", False))

    def connect(self) -> Go2Transport:
        """Bring up the link. Blocks until the data channel is validated.

        On failure the loop thread is torn down first: a half-open connection
        would make every later call hang on a dead loop.
        """
        if self._connected:
            return self

        self.conn = UnitreeWebRTCConnection(self.method, ip=self.ip, aes_128_key=self.aes_key)
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        def run_loop() -> None:
            assert self.loop is not None
            asyncio.set_event_loop(self.loop)
            self.loop.call_soon(ready.set)
            self.loop.run_forever()

        self._thread = threading.Thread(target=run_loop, name="go2-webrtc", daemon=True)
        self._thread.start()
        ready.wait(_JOIN_TIMEOUT)

        async def bring_up() -> None:
            assert self.conn is not None
            await self.conn.connect()
            if self.disable_traffic_saving:
                # Otherwise the robot throttles high-bandwidth topics.
                await self.conn.datachannel.disableTrafficSaving(True)
            if self.lidar_decoder:
                self.conn.datachannel.set_decoder(decoder_type=self.lidar_decoder)
            if self.motion_mode:
                await self.conn.datachannel.pub_sub.publish_request_new(
                    RTC_TOPIC["MOTION_SWITCHER"],
                    {"api_id": 1002, "parameter": {"name": self.motion_mode}},
                )

        try:
            self._run(bring_up(), timeout=self.settings.connect_timeout)
        except Exception as exc:
            self._teardown()
            raise self._explain(exc) from exc

        self._connected = True
        log.info("connected to %s", self.ip)
        return self

    def _explain(self, exc: Exception) -> ConnectionFailed:
        """Turn the transport's failure into one of ours.

        These are indistinguishable in the raw traceback and have different
        fixes, so they get different types.
        """
        name = type(exc).__name__
        text = str(exc)
        if "LocalSignalingPortError" in name or "not exposing a signaling port" in text:
            return SignallingUnavailable(
                f"{self.ip} is not serving WebRTC (tried 9991 and 8081).\n"
                f"  - is this the GO2 head unit, or the Jetson board? The head unit "
                f"has ONLY 9991 open; the Jetson never serves WebRTC\n"
                f"  - the robot may still be booting -- the port opens late\n"
                f"  - the head unit opens 9991 late in its boot; try again in a minute"
            )
        if "AesKeyRejected" in name or "AES-128 key" in text:
            return AuthenticationError(
                f"{self.ip} rejected the AES-128 key. It is per-device: check "
                f"GO2_AES_KEY matches this robot's serial "
                f"(`go2-credentials --email you@example.com`)."
            )
        return ConnectionFailed(
            f"could not connect to {self.ip}: {name}: {text}\n"
            f"  - the robot accepts ONE WebRTC client at a time; close the Unitree app"
        )

    def close(self) -> None:
        """Disconnect and stop the loop thread. Safe to call twice."""
        if self.conn is not None and self.loop is not None and self.loop.is_running():

            async def bring_down() -> None:
                assert self.conn is not None
                try:
                    await self.conn.disconnect()
                except Exception:  # noqa: BLE001 - teardown is best effort
                    log.debug("disconnect raised during teardown", exc_info=True)

            try:
                self._run(bring_down(), timeout=_JOIN_TIMEOUT)
            except Exception:  # noqa: BLE001
                log.debug("teardown timed out", exc_info=True)
        self._teardown()
        self._connected = False

    def _teardown(self) -> None:
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=_JOIN_TIMEOUT)
        self._thread = None

    def __enter__(self) -> Go2Transport:
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- thread bridge -----------------------------------------------------

    def _run(self, coro: Any, timeout: float | None = 10.0) -> Any:
        if self.loop is None:
            raise ConnectionFailed("not connected")
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def call_soon(self, fn: Callable[[], None]) -> None:
        """Run a plain function on the loop thread, fire and forget."""
        if self.loop is None:
            raise ConnectionFailed("not connected")
        self.loop.call_soon_threadsafe(fn)

    # -- pub / sub ---------------------------------------------------------

    def request(
        self, topic: str, api_id: int, parameter: Any = None, timeout: float = 10.0
    ) -> dict:
        """Send an api_id request and block for the robot's reply."""
        assert self.conn is not None
        options: dict[str, Any] = {"api_id": api_id}
        if parameter is not None:
            options["parameter"] = parameter
        return self._run(
            self.conn.datachannel.pub_sub.publish_request_new(topic, options), timeout=timeout
        )

    def publish(self, topic: str, data: Any, msg_type: str | None = None) -> None:
        """Fire a message with no reply expected."""
        assert self.conn is not None
        pub_sub = self.conn.datachannel.pub_sub
        self.call_soon(
            lambda: pub_sub.publish_without_callback(topic, data=data, msg_type=msg_type)
        )

    def subscribe(self, topic: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        """Subscribe to a topic; returns an unsubscribe function.

        The callback runs on the loop thread and receives the decoded message
        dict. Keep it to a copy-and-return -- see the module docstring.
        """
        assert self.conn is not None
        pub_sub = self.conn.datachannel.pub_sub

        with self._lock:
            first = topic not in self._callbacks
            self._callbacks.setdefault(topic, []).append(callback)

        if first:

            def dispatch(msg: dict) -> None:
                with self._lock:
                    callbacks = list(self._callbacks.get(topic, ()))
                for cb in callbacks:
                    try:
                        cb(msg)
                    except Exception:  # noqa: BLE001
                        # One bad subscriber must not kill the loop thread.
                        log.exception("subscriber for %s raised", topic)

            self.call_soon(lambda: pub_sub.subscribe(topic, dispatch))

        def unsubscribe() -> None:
            with self._lock:
                callbacks = self._callbacks.get(topic, [])
                if callback in callbacks:
                    callbacks.remove(callback)
                empty = not callbacks
                if empty:
                    self._callbacks.pop(topic, None)
            if empty:
                self.call_soon(lambda: pub_sub.unsubscribe(topic))

        return unsubscribe

    # -- convenience -------------------------------------------------------

    def motion_mode_now(self, timeout: float = 10.0) -> str | None:
        """Which motion controller is active (api 1001). Read-only.

        The best liveness probe available: it exercises the full request ->
        response round trip, so a sane answer means the data channel really
        works rather than merely being open.
        """
        response = self.request(RTC_TOPIC["MOTION_SWITCHER"], 1001, timeout=timeout)
        try:
            return json.loads(response["data"]["data"]).get("name") or "(none)"
        except (KeyError, TypeError, ValueError):
            return None

    def move(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> None:
        """One body-frame velocity command.

        The robot halts by itself ~0.5 s after the last command (firmware
        watchdog), so continuous motion means calling this on a timer. Provided
        because a capture sometimes needs the robot nudged to a better
        viewpoint; nothing in this package calls it for you.
        """
        self.publish(RTC_TOPIC["WIRELESS_CONTROLLER"], {"lx": -y, "ly": x, "rx": -yaw, "ry": 0})

    def stop_move(self) -> None:
        self.request(RTC_TOPIC["SPORT_MOD"], SPORT_CMD["StopMove"])


# ---------------------------------------------------------------------------
# The camera: a video track that pushes frames continuously once switched on,
# cached in a single slot. Frames carry an arrival stamp because a VPS reply
# lands hundreds of ms later -- pair an image with odometry AT CAPTURE TIME.
# ---------------------------------------------------------------------------


# Fixed by the hardware: another size did not come from this lens.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720


def quiet_decoder_warnings() -> None:
    """Silence aiortc's pre-keyframe decode warnings.

    A stream starts mid-GOP, so packets before the first keyframe cannot be
    decoded and each logs a WARNING. Real errors still come through.
    """
    logging.getLogger("aiortc.codecs.h264").setLevel(logging.ERROR)


class Go2Camera:
    """Newest front-camera frame, as BGR uint8 (OpenCV's layout).

    with Go2Transport(settings) as t, Go2Camera(t) as cam:
        frame = cam.wait_for_frame()
    """

    def __init__(
        self,
        transport: Go2Transport,
        on_frame: Callable[[np.ndarray, float], None] | None = None,
    ) -> None:
        self.transport = transport
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._stamp = 0.0
        self._seq = 0
        self._overwritten = 0
        self._started = False
        self._stop = threading.Event()
        self._reader: Any = None
        # Called on the loop thread for EVERY frame, unlike grab(). Same
        # don't-block rule as a topic callback.
        self._on_frame = on_frame

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> Go2Camera:
        """Register the reader, THEN switch the video on. The order matters.

        on_track awaits recv() once before calling any registered callback, and
        frames only flow after switchVideoChannel(True) -- that parked recv() is
        the window to register in. Reversed, you get a healthy connection and a
        permanently silent camera.
        """
        if self._started:
            return self
        conn = self.transport.conn
        if conn is None:
            raise RuntimeError("connect the transport before starting the camera")

        async def reader(track: Any) -> None:
            from aiortc.mediastreams import MediaStreamError

            try:
                while not self._stop.is_set():
                    frame = await track.recv()
                    self._put(frame)
            except MediaStreamError:
                log.debug("video track ended")

        self._reader = reader
        conn.video.add_track_callback(reader)
        self.transport.call_soon(lambda: conn.video.switchVideoChannel(True))
        self._started = True
        log.debug("video channel on")
        return self

    def stop(self) -> None:
        """Stop the video channel and drop the reader. Safe to call twice."""
        if not self._started:
            return
        self._stop.set()
        conn = self.transport.conn
        if conn is not None:
            with contextlib.suppress(ValueError):
                conn.video.track_callbacks.remove(self._reader)
            if self.transport.loop is not None and self.transport.loop.is_running():
                self.transport.call_soon(lambda: conn.video.switchVideoChannel(False))
        # The reader is parked in recv() and dies with the event loop;
        # start() builds a fresh one.
        self._started = False

    def __enter__(self) -> Go2Camera:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- frames ------------------------------------------------------------

    def _put(self, av_frame: Any) -> None:
        """Decode one av.VideoFrame into the cache. Runs on the loop thread."""
        # bgr24 from the decoder: the colour conversion happens in C.
        bgr = av_frame.to_ndarray(format="bgr24")
        stamp = time.time()
        with self._lock:
            if self._frame is not None:
                self._overwritten += 1
            self._frame = bgr
            self._stamp = stamp
            self._seq += 1
        if self._on_frame is not None:
            try:
                self._on_frame(bgr, stamp)
            except Exception:  # noqa: BLE001
                log.exception("camera tap raised")

    def grab(self) -> tuple[np.ndarray | None, float]:
        """(copy of the newest frame, its arrival time), or (None, 0.0)."""
        with self._lock:
            if self._frame is None:
                return None, 0.0
            return self._frame.copy(), self._stamp

    @property
    def seq(self) -> int:
        """Frames received so far. Compare across a sleep to measure the rate."""
        with self._lock:
            return self._seq

    @property
    def stats(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "received": self._seq,
                "overwritten": self._overwritten,
                "last": self._stamp,
            }

    def wait_for_frame(self, timeout: float = 20.0, after_seq: int | None = None) -> np.ndarray:
        """Block until a frame is available. Raises FrameTimeout.

        Pass after_seq=cam.seq to insist on a frame arriving AFTER this call --
        what you want when the robot has just moved.
        """
        floor = -1 if after_seq is None else after_seq
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._frame is not None and self._seq > floor:
                    return self._frame.copy()
            time.sleep(0.02)
        raise FrameTimeout(
            f"no frame within {timeout:.0f}s. The link is up but no video is "
            f"arriving -- the robot allows ONE video client at a time, so close "
            f"the Unitree app or any other session and retry."
        )

    def fresh_frame(self, settle: float = 0.4, timeout: float = 20.0) -> np.ndarray:
        """A frame taken at least `settle` seconds from now.

        Not about buffering: right after a move the image is motion-blurred and
        the legs are still settling.
        """
        start = self.seq
        time.sleep(settle)
        return self.wait_for_frame(timeout=timeout, after_seq=start)


__all__ = [
    "DATA_CHANNEL_TYPE",
    "MOTION_MODES",
    "RTC_TOPIC",
    "SPORT_CMD",
    "FRAME_HEIGHT",
    "FRAME_WIDTH",
    "Go2Camera",
    "Go2Transport",
    "quiet_decoder_warnings",
]
