"""Chat logic over the in-memory store. Knows nothing about HTTP."""

from datetime import UTC, datetime
from pathlib import Path

import json5

from app.schemas import Channel, Message, NewMessage, Store, User

SEED_PATH = Path(__file__).with_name("seed.jsonc")
# who the agent posts as: the API has no auth, so every new message comes from it
ASSISTANT = "ops-assistant"


# error messages are written for the agent: through MCP, `str(exc)` is what it reads
class ChatError(Exception):
    pass


class NotFound(ChatError):
    pass


def load_seed(now: datetime) -> Store:
    # json5 reads JSON plus // comments and trailing commas; `now` turns the seed's offsets into times
    return Store.model_validate(
        json5.loads(SEED_PATH.read_text()), context={"now": now}
    )


class Chat:
    def __init__(self, store: Store) -> None:
        self.store = store

    def users(self) -> list[User]:
        return self.store.users

    def channels(self) -> list[Channel]:
        return self.store.channels

    def messages(self, to: str) -> list[Message]:
        self._target(to)
        return [m for m in self.store.messages if m.to == to]

    def post(self, new: NewMessage) -> Message:
        self._target(new.to)
        message = Message(
            id=max((m.id for m in self.store.messages), default=0) + 1,
            to=new.to,
            author=ASSISTANT,
            text=new.text,
            sent_at=datetime.now(UTC),
        )
        self.store.messages.append(message)
        return message

    def _target(self, to: str) -> None:
        known = {c.name for c in self.store.channels} | {
            u.handle for u in self.store.users
        }
        if to not in known:
            raise NotFound(
                f"No channel or user {to}. Channels start with #, people with @."
            )
