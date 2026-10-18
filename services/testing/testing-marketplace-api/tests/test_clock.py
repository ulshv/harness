from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.clock import resolve_offset
from app.schemas import Order

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def order(ship_by: object) -> dict:
    lines = [{"sku": "GRN-HOME", "qty": 6}]
    return {
        "id": "114-1",
        "buyer": "B",
        "lines": lines,
        "ship_by": ship_by,
        "status": "unshipped",
    }


def test_offsets_resolve_against_now():
    assert resolve_offset("+6h", NOW) == datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    assert resolve_offset("-12d", NOW) == datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def test_seed_times_are_offsets():
    parsed = Order.model_validate(order("+6h"), context={"now": NOW})

    assert parsed.ship_by == datetime(2026, 10, 18, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "value", ["+2x", "2d", "2026-10-16T12:00:00Z", 0, "+99999999d"]
)
def test_a_malformed_offset_fails_the_seed(value):
    with pytest.raises(ValidationError):
        Order.model_validate(order(value), context={"now": NOW})
