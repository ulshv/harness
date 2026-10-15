from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.schemas import (
    LocationStock,
    Move,
    MoveResult,
    Order,
    OrderStatus,
    Product,
    Reservation,
    SkuStock,
    Store,
    StoredProduct,
)
from app.store import Conflict, NotFound, Unavailable, Warehouse

# Every handler is `async def`: FastAPI would run sync ones in a thread pool, concurrently. Async ones run one at
# a time on the event loop's thread, and the store never awaits mid-change, so no locks (with a single worker).
router = APIRouter()


async def get_warehouse(request: Request) -> Warehouse:
    return request.app.state.warehouse


WarehouseDep = Annotated[Warehouse, Depends(get_warehouse)]

_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
    Conflict: 409,
    Unavailable: 503,
}


# registered for the base class; Starlette finds the handler by walking the exception's MRO
async def warehouse_error(request: Request, exc: Exception) -> JSONResponse:
    # an unmapped domain error is our bug: 500, not a KeyError inside the handler
    status_code = _STATUS.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# response_model differs from the return type on purpose: it serializes only Product's fields, dropping `broken`
@router.get("/products", response_model=list[Product])
async def products(
    warehouse: WarehouseDep, q: str | None = None
) -> list[StoredProduct]:
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
async def order(warehouse: WarehouseDep, order_id: int) -> Order:
    return warehouse.order(order_id)


@router.post("/orders/{order_id}/reserve")
async def reserve(warehouse: WarehouseDep, order_id: int) -> Reservation:
    return warehouse.reserve(order_id)


@router.post("/orders/{order_id}/cancel")
async def cancel(warehouse: WarehouseDep, order_id: int) -> Order:
    return warehouse.cancel(order_id)


@router.post("/moves")
async def moves(warehouse: WarehouseDep, move: Move) -> MoveResult:
    return warehouse.move(move)


# the test panel for the eval runner; the MCP server won't expose it
@router.post("/_reset")
async def reset(warehouse: WarehouseDep) -> Store:
    return warehouse.reset()


@router.get("/_state")
async def state(warehouse: WarehouseDep) -> Store:
    return warehouse.store
