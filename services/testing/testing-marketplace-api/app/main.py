import asyncio
import random
from datetime import UTC, datetime

from fastapi import FastAPI, Request

from app import api
from app.schemas import Store
from app.store import Marketplace, MarketplaceError, load_seed

# a real marketplace API answers after a network and database round trip, like testing-wms-api (history 010.4)
LATENCY_SECONDS = (0.1, 0.5)


# the store parameter is the seam for tests: each test app gets its own fresh store; tests skip the latency
def create_app(
    store: Store | None = None, latency: tuple[float, float] | None = None
) -> FastAPI:
    app = FastAPI(title="testing-marketplace-api")
    app.state.marketplace = Marketplace(store or load_seed(datetime.now(UTC)))
    app.include_router(api.router)
    app.add_exception_handler(MarketplaceError, api.marketplace_error)
    if latency:
        _add_latency(app, latency)
    return app


# asyncio.sleep yields the event loop, so concurrent requests overlap like they would on a pooled database
def _add_latency(app: FastAPI, latency: tuple[float, float]) -> None:
    @app.middleware("http")
    async def simulate_latency(request: Request, call_next):
        await asyncio.sleep(random.uniform(*latency))
        return await call_next(request)


# uvicorn's target (`app.main:app`); a broken seed fails the boot, not the first request
app = create_app(latency=LATENCY_SECONDS)
