import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storage  # noqa: E402


@pytest.fixture
def conn():
    connection = storage.connect(":memory:")
    yield connection
    connection.close()
