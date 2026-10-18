from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import load_seed

# a fixed startup time: the seed's offsets resolve to the same instants in every run
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


# a fresh app per test: each gets its own store loaded from the seed
@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(load_seed(NOW)))
