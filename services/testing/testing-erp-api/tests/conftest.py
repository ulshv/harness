from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import load_seed


# a fresh app per test, loaded at the real time: `overdue` compares with the real clock, so a fixed startup
# time would turn "due in 20 days" into "overdue" once the calendar passes it
@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(load_seed(datetime.now(UTC))))
