"""Versions come from git tags, so the derivation gets a test.

hatch-vcs runs from the package directory. Without an explicit root it never
finds .git, falls back to fallback_version, and ignores the tag entirely.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PYPROJECTS = sorted(REPO.glob("packages/*/pyproject.toml"))


def test_there_are_packages_to_check():
    assert PYPROJECTS


def test_hatch_vcs_points_at_the_repo_root():
    for pyproject in PYPROJECTS:
        assert 'raw-options.root = "../.."' in pyproject.read_text(), pyproject
        assert (pyproject.parent / ".." / "..").resolve() == REPO, pyproject


def test_tag_prefix_is_the_package_directory_name():
    """release.yml derives the directory from the tag, so the two must agree."""
    for pyproject in PYPROJECTS:
        name = pyproject.parent.name
        text = pyproject.read_text()
        assert f"^{name}-v(?P<version>.+)$" in text, name
        assert f"--match '{name}-v*'" in text, name


def test_release_workflow_knows_every_package():
    workflow = (REPO / ".github/workflows/release.yml").read_text()
    for pyproject in PYPROJECTS:
        assert f"{pyproject.parent.name})" in workflow, pyproject.parent.name
