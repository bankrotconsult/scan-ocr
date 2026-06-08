from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request

from src.admin_flask.app import init_admin
from src.config.base import BaseConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("start!!!")

    yield

    print("end!!!")


app = FastAPI(
    lifespan=lifespan,
)


if not BaseConfig.DEBUG:
    @app.middleware("http")
    async def force_https_scheme(request: Request, call_next):
        request.scope["scheme"] = "https"
        return await call_next(request)


init_admin(app)


from src.files.routers import router as files_router


app.include_router(files_router)
