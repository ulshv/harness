from datetime import UTC, datetime

from fastapi import FastAPI

from app import api
from app.schemas import Store
from app.store import Marketplace, MarketplaceError, load_seed


# the store parameter is the seam for tests: each test app gets its own fresh store
def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="testing-marketplace-api")
    app.state.marketplace = Marketplace(store or load_seed(datetime.now(UTC)))
    app.include_router(api.router)
    app.add_exception_handler(MarketplaceError, api.marketplace_error)
    return app


# uvicorn's target (`app.main:app`); a broken seed fails the boot, not the first request
app = create_app()
