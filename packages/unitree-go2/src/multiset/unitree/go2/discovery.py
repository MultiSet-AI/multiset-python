"""Find a Go2 on the local network.

Two independent methods, because the first one does not always work:

`find_serial()` asks over multicast and gets the serial for free, but the
responder does not run on every firmware -- a robot can be up, listening on
9991 and perfectly reachable while answering nothing.

The sweep is the fallback. A Go2 head unit is the host with 9991 open and SSH
closed; the Jetson carrier board is the reverse. That difference is the whole
signature, and it is what tells GO2_IP from the address that merely looks like
a robot.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

log = logging.getLogger(__name__)

SIGNALLING_PORT = 9991
JETSON_PORTS = (22, 80)


@dataclass(frozen=True)
class Host:
    """One machine that looks like part of a Go2."""

    ip: str
    role: str  # "go2" | "jetson"
    serial: str | None = None
    ports: tuple[int, ...] = ()

    @property
    def is_robot(self) -> bool:
        """True for the head unit -- the only host that serves WebRTC."""
        return self.role == "go2"

    def __str__(self) -> str:
        ports = ",".join(str(p) for p in self.ports)
        serial = f"  sn={self.serial}" if self.serial else ""
        return f"{self.ip:<15} {self.role:<7}{serial}  ports: {ports or '-'}"


def local_subnet() -> ipaddress.IPv4Network | None:
    """This machine's own /24, or None when it has no usable address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connectionless: this picks the default route without sending anything.
        sock.connect(("8.8.8.8", 53))
        address = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
    try:
        return ipaddress.ip_network(f"{address}/24", strict=False)  # type: ignore[return-value]
    except ValueError:
        return None


def port_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    """One TCP connect. True when something accepts.

    Both halves of a Go2 DROP packets to a closed port rather than refusing
    them, so a closed port costs the full timeout. That is what shapes the scan
    below -- there is no cheap way to ask "is anything there?".
    """
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
    except OSError:
        return False
    else:
        return True
    finally:
        sock.close()


def classify(ip: str, timeout: float = 1.0) -> Host | None:
    """Which half of a Go2 this address is, or None when it is neither.

    Hosts matching no signature are dropped rather than reported. This looks for
    a robot; it is not a network inventory tool.
    """
    open_ports = tuple(p for p in (SIGNALLING_PORT, *JETSON_PORTS) if port_open(ip, p, timeout))
    if SIGNALLING_PORT in open_ports:
        return Host(ip=ip, role="go2", ports=open_ports)
    if all(p in open_ports for p in JETSON_PORTS):
        return Host(ip=ip, role="jetson", ports=open_ports)
    return None


def scan_subnet(
    subnet: str | ipaddress.IPv4Network | None = None,
    *,
    timeout: float = 1.0,
    workers: int = 64,
) -> list[Host]:
    """Every Go2-shaped host on a subnet, head units first.

    Two passes, because a closed port costs a full timeout and probing three
    ports on every address triples the wall clock for nothing.

    The first pass looks only for 9991. If it finds a head unit the scan is
    done -- that is the address you came for. Only when it finds none does the
    second pass look for the Jetson, which turns a bare "no robot found" into
    "the board is up but the head unit is not", the failure that looks like a
    broken robot.

    Defaults to this machine's own /24: roughly four seconds, or eight when
    there is no head unit to find.
    """
    network = ipaddress.ip_network(subnet, strict=False) if subnet else local_subnet()
    if network is None:
        log.debug("no local subnet to scan")
        return []
    addresses = [str(h) for h in network.hosts()]
    log.debug("scanning %d addresses on %s", len(addresses), network)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        hits = pool.map(lambda ip: port_open(ip, SIGNALLING_PORT, timeout), addresses)
        robots = [
            Host(ip=ip, role="go2", ports=(SIGNALLING_PORT,))
            for ip, found in zip(addresses, hits, strict=True)
            if found
        ]
        if robots:
            return sorted(robots, key=lambda h: h.ip)

        log.debug("no head unit; looking for a Jetson board")
        boards = pool.map(lambda ip: port_open(ip, JETSON_PORTS[0], timeout), addresses)
        candidates = [ip for ip, found in zip(addresses, boards, strict=True) if found]
        jetsons = [
            Host(ip=ip, role="jetson", ports=JETSON_PORTS)
            for ip in candidates
            if port_open(ip, JETSON_PORTS[1], timeout)
        ]
    return sorted(jetsons, key=lambda h: h.ip)


def find_robots(
    *,
    subnet: str | ipaddress.IPv4Network | None = None,
    timeout: float = 1.0,
    workers: int = 64,
) -> list[Host]:
    """Robots on this network, head units first.

    Sweeps for the port only a Go2 head unit opens. That is 254 TCP connects on
    your own LAN -- unremarkable at home, and capable of tripping intrusion
    detection on a corporate network.

    An empty list is a normal answer. Read the address off your router instead.

    There is a second method: `credentials.find_serial()` asks over multicast
    and returns the serial for free. It is not used here because the responder
    does not run on every firmware -- a robot can be powered on, listening on
    9991 and perfectly reachable while answering nothing. Try it if you like;
    the serial is also on the robot's own sticker, and in the cloud reply that
    `go2-credentials` already prints.
    """
    return scan_subnet(subnet, timeout=timeout, workers=workers)


__all__ = [
    "JETSON_PORTS",
    "SIGNALLING_PORT",
    "Host",
    "classify",
    "find_robots",
    "local_subnet",
    "port_open",
    "scan_subnet",
]
