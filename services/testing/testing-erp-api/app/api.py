from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.schemas import (
    Channel,
    Customer,
    Hold,
    NewSalesOrder,
    PurchaseOrder,
    PurchaseStatus,
    SalesOrder,
    SalesStatus,
    Store,
    WmsLink,
)
from app.store import Conflict, Erp, NotFound

# async handlers run one at a time on the event loop's thread and the store never awaits mid-change,
# so no locks (with a single worker), as in testing-wms-api
router = APIRouter()


async def get_erp(request: Request) -> Erp:
    return request.app.state.erp


ErpDep = Annotated[Erp, Depends(get_erp)]

_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
    Conflict: 409,
}


# registered for the base class; Starlette finds the handler by walking the exception's MRO
async def erp_error(request: Request, exc: Exception) -> JSONResponse:
    # an unmapped domain error is our bug: 500, not a KeyError inside the handler
    status_code = _STATUS.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/customers")
async def customers(erp: ErpDep) -> list[Customer]:
    return erp.customers()


@router.get("/customers/{customer_id}")
async def customer(erp: ErpDep, customer_id: str) -> Customer:
    return erp.customer(customer_id)


@router.get("/sales-orders")
async def sales_orders(
    erp: ErpDep, status: SalesStatus | None = None, channel: Channel | None = None
) -> list[SalesOrder]:
    return erp.sales_orders(status, channel)


@router.get("/sales-orders/{order_id}")
async def sales_order(erp: ErpDep, order_id: str) -> SalesOrder:
    return erp.sales_order(order_id)


@router.post("/sales-orders", status_code=201)
async def create_sales_order(erp: ErpDep, new: NewSalesOrder) -> SalesOrder:
    return erp.create(new)


@router.post("/sales-orders/{order_id}/hold")
async def hold(erp: ErpDep, order_id: str, body: Hold) -> SalesOrder:
    return erp.hold(order_id, body.reason)


@router.post("/sales-orders/{order_id}/wms-order")
async def link_wms_order(erp: ErpDep, order_id: str, body: WmsLink) -> SalesOrder:
    return erp.link_wms_order(order_id, body.wms_order_id)


@router.get("/purchase-orders")
async def purchase_orders(
    erp: ErpDep, status: PurchaseStatus | None = None
) -> list[PurchaseOrder]:
    return erp.purchase_orders(status)


@router.get("/purchase-orders/{order_id}")
async def purchase_order(erp: ErpDep, order_id: str) -> PurchaseOrder:
    return erp.purchase_order(order_id)


# the whole world, to check what the agent changed; the MCP server won't expose it.
# No /_reset: a restart reloads the seed
@router.get("/_state")
async def state(erp: ErpDep) -> Store:
    return erp.store
