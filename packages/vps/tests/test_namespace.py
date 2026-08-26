"""The namespace itself is load-bearing, so it gets a test.

An __init__.py anywhere in a namespace directory turns it into a regular package
and makes every SIBLING distribution invisible -- multiset.vps installed, then
`import multiset.unitree.go2.dimos` raises ModuleNotFoundError with nothing in
the traceback pointing at the cause. Cheap to prevent, miserable to debug.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: Every shared level of the import path. A distribution owns the LEAF below
#: these; nothing owns these.
NAMESPACE_DIRS = (
    "packages/*/src/multiset",
    "packages/*/src/multiset/unitree",
    "packages/*/src/multiset/unitree/go2",
)


def test_no_init_in_any_namespace_directory():
    offenders = [
        str(p.relative_to(REPO))
        for pattern in NAMESPACE_DIRS
        for p in REPO.glob(f"{pattern}/__init__.py")
    ]
    assert offenders == [], (
        f"{offenders} makes a shared namespace a regular package; every sibling "
        f"multiset.* distribution becomes unimportable."
    )


def test_every_package_declares_the_src_namespace_root():
    """Each wheel must ship src/multiset, not src/multiset/<leaf>."""
    pyprojects = list(REPO.glob("packages/*/pyproject.toml"))
    assert pyprojects, "no packages found -- is REPO pointing at the right place?"
    for pyproject in pyprojects:
        assert 'packages = ["src/multiset"]' in pyproject.read_text(), pyproject
