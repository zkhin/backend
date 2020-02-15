"""
Tests for generating album art.

These tests mainly intended to just ensure the art-generating logic
doesn't crash, not that the output has the correct visual form.
"""

from contextlib import ExitStack
from os import path
import random

import pytest

from app.models.album import art

grant_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant.jpg')
grant_horz_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-horizontal.jpg')
grant_vert_path = path.join(path.dirname(__file__), '..', '..', 'fixtures', 'grant-vertical.jpg')


@pytest.fixture
def image_bufs():
    "Yields 20 buffers of image data"
    image_paths = [random.choice([grant_path, grant_horz_path, grant_vert_path]) for i in range(20)]
    with ExitStack() as stack:
        yield [stack.enter_context(open(image_path, 'rb')) for image_path in image_paths]


def test_generate_basic_grid_failures(image_bufs):
    for i in (0, 1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20):
        with pytest.raises(AssertionError):
            art.generate_basic_grid(image_bufs[:i])


def test_genearte_basic_grid_successes(image_bufs):
    assert art.generate_basic_grid(image_bufs[:4]).read(1)
    assert art.generate_basic_grid(image_bufs[:9]).read(1)
    assert art.generate_basic_grid(image_bufs[:16]).read(1)


def test_generate_zoomed_grid_failures(image_bufs):
    for i in (0, 1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20):
        with pytest.raises(AssertionError):
            art.generate_zoomed_grid(image_bufs[:i])


def test_genearte_zoomed_grid_successes(image_bufs):
    assert art.generate_zoomed_grid(image_bufs[:4]).read(1)
    assert art.generate_zoomed_grid(image_bufs[:9]).read(1)
    assert art.generate_zoomed_grid(image_bufs[:16]).read(1)
