from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.schemas import Channel, Message, NewMessage, Store, User
from app.store import Chat, NotFound

# async handlers run one at a time on the event loop's thread and the store never awaits mid-change,
# so no locks (with a single worker), as in testing-wms-api
router = APIRouter()


async def get_chat(request: Request) -> Chat:
    return request.app.state.chat


ChatDep = Annotated[Chat, Depends(get_chat)]

_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
}


# registered for the base class; Starlette finds the handler by walking the exception's MRO
async def chat_error(request: Request, exc: Exception) -> JSONResponse:
    # an unmapped domain error is our bug: 500, not a KeyError inside the handler
    status_code = _STATUS.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/channels")
async def channels(chat: ChatDep) -> list[Channel]:
    return chat.channels()


@router.get("/users")
async def users(chat: ChatDep) -> list[User]:
    return chat.users()


# `to` is a query param, not a path segment: `#` in a URL path would start the fragment
@router.get("/messages")
async def messages(chat: ChatDep, to: str) -> list[Message]:
    return chat.messages(to)


@router.post("/messages", status_code=201)
async def post(chat: ChatDep, new: NewMessage) -> Message:
    return chat.post(new)


# the whole world, to check what the agent changed; the MCP server won't expose it.
# No /_reset: a restart reloads the seed
@router.get("/_state")
async def state(chat: ChatDep) -> Store:
    return chat.store
