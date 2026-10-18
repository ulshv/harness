from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.schemas import (
    LocationStock,
    Move,
    MoveResult,
    NewOrder,
    Order,
    OrderStatus,
    Product,
    Reservation,
    SkuStock,
    Store,
)
from app.store import Conflict, NotFound, Warehouse

# Every handler is `async def`: FastAPI would run sync ones in a thread pool, concurrently. Async ones run one at
# a time on the event loop's thread, and the store never awaits mid-change, so no locks (with a single worker).
router = APIRouter()


async def get_warehouse(request: Request) -> Warehouse:
    return request.app.state.warehouse


WarehouseDep = Annotated[Warehouse, Depends(get_warehouse)]

_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
    Conflict: 409,
}


# registered for the base class; Starlette finds the handler by walking the exception's MRO
async def warehouse_error(request: Request, exc: Exception) -> JSONResponse:
    # an unmapped domain error is our bug: 500, not a KeyError inside the handler
    status_code = _STATUS.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/products")
async def products(warehouse: WarehouseDep, q: str | None = None) -> list[Product]:
    return warehouse.products(q)


@router.get("/locations")
async def locations(warehouse: WarehouseDep) -> list[LocationStock]:
    return warehouse.locations()


@router.get("/stock/{sku}")
async def stock(warehouse: WarehouseDep, sku: str) -> SkuStock:
    return warehouse.stock(sku)


# a Literal-typed query param: FastAPI answers 422 for anything outside it
@router.get("/orders")
async def orders(
    warehouse: WarehouseDep, status: OrderStatus | None = None
) -> list[Order]:
    return warehouse.orders(status)


@router.get("/orders/{order_id}")
async def order(warehouse: WarehouseDep, order_id: str) -> Order:
    return warehouse.order(order_id)


@router.post("/orders", status_code=201)
async def create_order(warehouse: WarehouseDep, new: NewOrder) -> Order:
    return warehouse.create(new)


@router.post("/orders/{order_id}/reserve")
async def reserve(warehouse: WarehouseDep, order_id: str) -> Reservation:
    return warehouse.reserve(order_id)


@router.post("/orders/{order_id}/release")
async def release(warehouse: WarehouseDep, order_id: str) -> Order:
    return warehouse.release(order_id)


@router.post("/orders/{order_id}/cancel")
async def cancel(warehouse: WarehouseDep, order_id: str) -> Order:
    return warehouse.cancel(order_id)


@router.post("/moves")
async def moves(warehouse: WarehouseDep, move: Move) -> MoveResult:
    return warehouse.move(move)


# the whole world, to check what the agent changed; the MCP server won't expose it.
# No /_reset: a restart reloads the seed
@router.get("/_state")
async def state(warehouse: WarehouseDep) -> Store:
    return warehouse.store
