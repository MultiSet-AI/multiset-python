"""Discovery, with the network stubbed out.

Port probing is monkeypatched, so these assert the classification rules rather
than whatever happens to be on the machine's LAN.
"""

from __future__ import annotations

import pytest
from multiset.unitree.go2.dimos import discovery
from multiset.unitree.go2.dimos.discovery import Host, classify, find_robots, scan_subnet


@pytest.fixture
def lan(monkeypatch):
    """A fake network: {ip: [open ports]}."""
    table: dict[str, list[int]] = {}

    monkeypatch.setattr(
        discovery, "port_open", lambda ip, port, _t=1.0: port in table.get(ip, [])
    )
    return table


def test_head_unit_is_the_host_with_9991(lan):
    """Only port 9991 open -- this is GO2_IP."""
    lan["192.168.1.114"] = [9991]
    host = classify("192.168.1.114")
    assert host == Host(ip="192.168.1.114", role="go2", ports=(9991,))
    assert host.is_robot


def test_ssh_plus_web_is_the_jetson(lan):
    """The board with SSH and the upgrade UI never serves WebRTC."""
    lan["192.168.1.10"] = [22, 80]
    host = classify("192.168.1.10")
    assert host is not None
    assert host.role == "jetson"
    assert not host.is_robot


def test_9991_wins_when_both_are_open(lan):
    """A single host serving both is still the one to point GO2_IP at."""
    lan["192.168.1.50"] = [22, 80, 9991]
    host = classify("192.168.1.50")
    assert host is not None
    assert host.role == "go2"


def test_bare_ssh_is_not_a_robot(lan):
    """A NAS or a router must not be reported. Both Jetson ports are required."""
    lan["192.168.1.7"] = [22]
    assert classify("192.168.1.7") is None


def test_unrelated_hosts_are_dropped(lan):
    lan["192.168.1.3"] = [443, 8080]
    assert classify("192.168.1.3") is None


def test_a_found_head_unit_skips_the_jetson_pass(lan, monkeypatch):
    """The second pass is the expensive one; finding 9991 must skip it."""
    lan["192.168.1.114"] = [9991]
    lan["192.168.1.130"] = [22, 80]
    probed: list[int] = []
    real = discovery.port_open
    monkeypatch.setattr(
        discovery,
        "port_open",
        lambda ip, port, t=1.0: (probed.append(port), real(ip, port, t))[1],
    )
    found = discovery.scan_subnet("192.168.1.0/24", workers=16)
    assert [h.ip for h in found] == ["192.168.1.114"]
    assert set(probed) == {discovery.SIGNALLING_PORT}


def test_the_jetson_is_reported_when_no_head_unit_answers(lan):
    """Turns "no robot found" into "the board is up, the head unit is not"."""
    lan["192.168.1.130"] = [22, 80]
    found = discovery.scan_subnet("192.168.1.0/24", workers=16)
    assert [(h.ip, h.role) for h in found] == [("192.168.1.130", "jetson")]


def test_two_head_units_are_both_reported(lan):
    """Two robots on one LAN is a real setup; the caller has to choose."""
    lan["192.168.1.114"] = [9991]
    lan["192.168.1.115"] = [9991]
    found = scan_subnet("192.168.1.0/24", workers=16)
    assert [h.ip for h in found] == ["192.168.1.114", "192.168.1.115"]


def test_a_subnet_without_the_robot_finds_nothing(lan):
    lan["192.168.1.114"] = [9991]
    assert scan_subnet("10.0.0.0/29", workers=4) == []


def test_find_robots_sweeps_without_asking_multicast(lan):
    """Multicast is deliberately off the default path: not every firmware answers."""
    lan["192.168.1.114"] = [9991]
    hosts = find_robots(subnet="192.168.1.0/24", workers=16)
    assert [h.ip for h in hosts] == ["192.168.1.114"]
    assert hosts[0].serial is None  # a sweep cannot learn it; the cloud has it


def test_find_robots_on_an_empty_network(lan):
    """An empty list is a normal answer, not an error."""
    lan["192.168.1.7"] = [443]
    assert find_robots(subnet="192.168.1.0/24", workers=16) == []
