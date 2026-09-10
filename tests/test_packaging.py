"""An adapter must not admit a core version that lacks what it imports.

This is the failure only users see: pip honours the pin, resolves an older
core, and the package dies at import. Development never sees it, because it
always runs against the workspace.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADAPTERS = sorted(p for p in REPO.glob("packages/*/pyproject.toml") if p.parent.name != "vps")


def _core_pin(pyproject: Path) -> str:
    """The multiset-vps requirement. Read as text: tomllib is 3.11+."""
    match = re.search(r'"(multiset-vps[^"]*)"', pyproject.read_text())
    assert match, f"{pyproject} does not depend on multiset-vps"
    return match.group(1)


def _project_name(pyproject: Path) -> str:
    match = re.search(r'(?m)^name = "([^"]+)"', pyproject.read_text())
    assert match, f"{pyproject} has no project name"
    return match.group(1)


def _lower_bound(spec: str) -> tuple[int, int, int]:
    """The >= floor, padded to three parts.

    ">=0.1" means 0.1.0, tagged `vps-v0.1.0`. Unpadded, the lookup misses the
    tag and the check passes in silence -- for exactly the wrong pin shape.
    """
    match = re.search(r">=\s*([0-9][0-9.]*)", spec)
    assert match, f"no lower bound in {spec!r}"
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _names_imported_from_core(package_dir: Path) -> set[str]:
    names: set[str] = set()
    for source in (package_dir / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module == "multiset.vps":
                names.update(alias.name for alias in node.names)
    return names


def _core_exports_at(tag: str) -> set[str] | None:
    """__all__ of multiset.vps as of a released tag, or None if it is unreleased."""
    show = subprocess.run(
        ["git", "show", f"{tag}:packages/vps/src/multiset/vps/__init__.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if show.returncode != 0:
        return None
    for node in ast.walk(ast.parse(show.stdout)):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "__all__" for t in node.targets
        ):
            return {
                element.value
                for element in node.value.elts  # type: ignore[attr-defined]
                if isinstance(element, ast.Constant)
            }
    return None


def test_there_are_adapters_to_check():
    assert ADAPTERS


def test_every_adapter_pins_a_core_that_has_what_it_imports():
    unchecked: list[str] = []
    for pyproject in ADAPTERS:
        package = pyproject.parent
        spec = _core_pin(pyproject)
        floor = _lower_bound(spec)
        tag = "vps-v" + ".".join(str(part) for part in floor)
        exports = _core_exports_at(tag)
        if exports is None:
            unchecked.append(f"{package.name} -> {tag}")  # floor unreleased
            continue
        needed = _names_imported_from_core(package)
        missing = sorted(needed - exports)
        assert not missing, (
            f"{package.name} pins '{spec}', which allows multiset-vps "
            f"{'.'.join(str(p) for p in floor)} -- but that release has no "
            f"{missing}. A user's pip install would resolve it and then fail at "
            f"import. Raise the lower bound."
        )
    if unchecked:
        print(f"\n  (floors not yet released, so unverified: {unchecked})")


def test_release_workflow_knows_every_package():
    """A package the release workflow cannot resolve can never be released."""
    workflow = (REPO / ".github/workflows/release.yml").read_text()
    for pyproject in REPO.glob("packages/*/pyproject.toml"):
        assert f"{pyproject.parent.name})" in workflow, (
            f"release.yml has no case branch for '{pyproject.parent.name}'; "
            f"tagging it would fail with 'unknown tag prefix'."
        )


def test_ci_builds_every_package():
    workflow = (REPO / ".github/workflows/ci.yml").read_text()
    for pyproject in REPO.glob("packages/*/pyproject.toml"):
        name = _project_name(pyproject)
        assert name in workflow, f"ci.yml never builds {name}"
