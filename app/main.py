import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.admin.routes import admin_router
from app.api.v1.auth.routes import auth_router
from app.api.v1.client.routes import client_router
from app.api.v1.contract.routes import contract_router
from app.api.v1.engineer.routes import engineer_router
from app.core.exceptions import register_exceptions
from app.core.logger import setup_logger
from app.core.middlewares import register_middlewares
from app.core.template_registry import TemplateRegistry
from app.database.postgres import init_db
from app.database.redis import init_redis
from app.scripts.seed import seed_admin

app_logger = setup_logger("app.lifecycle")


def main(*, use_lifespan: bool = True, enable_middlewares: bool = True):
    lifespan_context = None

    if use_lifespan:

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Application lifecycle events"""
            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            app_logger.info("🚀 Server starting...")
            await init_db()
            await init_redis()
            await seed_admin()
            yield
            app_logger.info("👋 Server stopped...")

        lifespan_context = lifespan

    version = "v1"
    api_version = f"/api/{version}"

    app = FastAPI(
        swagger="2.0",
        title="switch Fiji IoT",
        description="Switch Fiji IoT Backend server",
        version=version,
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/mit"},
        docs_url=f"{api_version}/docs",
        openapi_url=f"/api/{version}/openapi.json",
        lifespan=lifespan_context,
    )

    register_exceptions(app)
    if enable_middlewares:
        register_middlewares(app)

    template_registry = TemplateRegistry()
    template_registry.mount_static(app=app)

    app.include_router(auth_router, prefix=f"{api_version}")
    app.include_router(admin_router, prefix=f"{api_version}")
    app.include_router(engineer_router, prefix=f"{api_version}")
    app.include_router(client_router, prefix=f"{api_version}")
    app.include_router(contract_router, prefix=f"{api_version}")

    return app


app = main()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
