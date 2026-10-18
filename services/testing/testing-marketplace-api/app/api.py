from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.schemas import Listing, Order, OrderStatus, QuantityUpdate, Store
from app.store import Marketplace, NotFound

# async handlers run one at a time on the event loop's thread and the store never awaits mid-change,
# so no locks (with a single worker), as in testing-wms-api
router = APIRouter()


async def get_marketplace(request: Request) -> Marketplace:
    return request.app.state.marketplace


MarketplaceDep = Annotated[Marketplace, Depends(get_marketplace)]

_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
}


# registered for the base class; Starlette finds the handler by walking the exception's MRO
async def marketplace_error(request: Request, exc: Exception) -> JSONResponse:
    # an unmapped domain error is our bug: 500, not a KeyError inside the handler
    status_code = _STATUS.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/orders")
async def orders(
    marketplace: MarketplaceDep, status: OrderStatus | None = None
) -> list[Order]:
    return marketplace.orders(status)


@router.get("/orders/{order_id}")
async def order(marketplace: MarketplaceDep, order_id: str) -> Order:
    return marketplace.order(order_id)


@router.get("/listings")
async def listings(marketplace: MarketplaceDep) -> list[Listing]:
    return marketplace.listings()


@router.get("/listings/{sku}")
async def listing(marketplace: MarketplaceDep, sku: str) -> Listing:
    return marketplace.listing(sku)


@router.put("/listings/{sku}/quantity")
async def set_quantity(
    marketplace: MarketplaceDep, sku: str, body: QuantityUpdate
) -> Listing:
    return marketplace.set_quantity(sku, body.quantity)


# the whole world, to check what the agent changed; the MCP server won't expose it.
# No /_reset: a restart reloads the seed
@router.get("/_state")
async def state(marketplace: MarketplaceDep) -> Store:
    return marketplace.store
