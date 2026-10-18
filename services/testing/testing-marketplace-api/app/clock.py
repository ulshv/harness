"""Seed times are offsets from startup ("+6h", "-2d"), so every run of the demo looks equally fresh."""

import re
from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BeforeValidator, ValidationInfo

OFFSET = re.compile(r"([+-])(\d+)([hd])")
UNITS = {"h": "hours", "d": "days"}


def resolve_offset(value: str, now: datetime) -> datetime:
    match = OFFSET.fullmatch(value)
    if match is None:
        raise ValueError(f"{value!r} is not an offset like +6h or -2d")
    sign, amount, unit = match.groups()
    try:
        delta = timedelta(**{UNITS[unit]: int(amount)})
        return now + delta if sign == "+" else now - delta
    except OverflowError as exc:  # "+99999999d": past datetime's range
        raise ValueError(f"{value!r} is too far from now") from exc


# with `now` in the validation context (loading the seed) a time must be an offset; without it (an API body)
# pydantic parses ISO 8601 as usual. The context reaches nested models, so one validate call covers the seed
def _from_offset(value: object, info: ValidationInfo) -> object:
    now = (info.context or {}).get("now")
    if now is None:
        return value
    # a number would pass as a Unix timestamp: an absolute time that breaks "every run looks fresh".
    # ValueError, not TypeError: pydantic turns only ValueError/AssertionError into a ValidationError
    if not isinstance(value, str):
        raise ValueError(f"seed times are offsets like +6h or -2d, not {value!r}")  # noqa: TRY004
    return resolve_offset(value, now)


Moment = Annotated[datetime, BeforeValidator(_from_offset)]
