"""Fixtures shared by the files under tests/ (the repo-wide setup is in the root conftest.py)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.gis_profiles import PROFILES, profile_env


@pytest.fixture(params=PROFILES)
def profile(request: pytest.FixtureRequest) -> Iterator[str]:
    """Each GIS profile in turn, with MAPLE_GIS set for the whole test (calls read it too)."""
    with profile_env(request.param):
        yield request.param
