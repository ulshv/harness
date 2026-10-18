from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.clock import resolve_offset
from app.schemas import Message

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def message(sent_at: object) -> dict:
    return {"id": 1, "to": "#ops", "author": "@tom", "text": "Hi", "sent_at": sent_at}


def test_offsets_resolve_against_now():
    assert resolve_offset("+6h", NOW) == datetime(2026, 10, 18, 18, 0, tzinfo=UTC)
    assert resolve_offset("-12d", NOW) == datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def test_seed_times_are_offsets():
    parsed = Message.model_validate(message("-2d"), context={"now": NOW})

    assert parsed.sent_at == datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "value", ["+2x", "2d", "2026-10-16T12:00:00Z", 0, "+99999999d"]
)
def test_a_malformed_offset_fails_the_seed(value):
    with pytest.raises(ValidationError):
        Message.model_validate(message(value), context={"now": NOW})
