import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse

from src.admin_flask.app import init_admin
from src.config.base import BaseConfig

_INDEX_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.files.routers import recover_uploads
    await recover_uploads()
    yield


app = FastAPI(lifespan=lifespan)


if not BaseConfig.DEBUG:
    @app.middleware("http")
    async def force_https_scheme(request: Request, call_next):
        request.scope["scheme"] = "https"
        return await call_next(request)


init_admin(app)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(_INDEX_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())


from src.files.routers import router as files_router
from src.split.routers import router as split_router

app.include_router(files_router)
app.include_router(split_router)
