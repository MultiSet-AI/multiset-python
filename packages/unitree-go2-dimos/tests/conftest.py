"""Test configuration.

Everything here runs without a robot, without credentials and without the
internet. Anything that needs hardware is marked and deselected by default --
see pyproject's addopts.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def frame_720p() -> np.ndarray:
    """A 1280x720 BGR frame with structure, so a remap has something to move."""
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)
    image[300:420, :, :] = 255  # a bright band
    image[:, 620:660, :] = 0  # a dark stripe
    return image
