from pydantic import BaseModel, Field

from app.clock import Moment


class User(BaseModel):
    handle: str
    name: str
    role: str


class Channel(BaseModel):
    name: str
    topic: str


class Message(BaseModel):
    id: int
    # a channel (`#sales`) or a person's handle (`@maria`) for a direct message
    to: str
    author: str
    text: str
    sent_at: Moment


# the whole workspace: seed.jsonc, the in-memory state and GET /_state share this one shape
class Store(BaseModel):
    users: list[User]
    channels: list[Channel]
    messages: list[Message]


class NewMessage(BaseModel):
    to: str
    text: str = Field(min_length=1)
