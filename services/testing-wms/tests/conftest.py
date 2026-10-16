import pytest
from fastapi.testclient import TestClient

from app.main import create_app


# a fresh app per test: each gets its own store loaded from the seed
@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
