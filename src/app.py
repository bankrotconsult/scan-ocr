import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse

from src.admin_flask.app import init_admin
from src.config.base import BaseConfig

_INDEX_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

# Интервал периодического восстановления осиротевших файлов в uploads/
RECOVERY_INTERVAL_SEC = 60 * 5


async def _recovery_loop() -> None:
    """Периодически запускать recover_uploads, чтобы орфаны подхватывались без рестарта контейнера."""
    from src.files.routers import recover_uploads

    while True:
        try:
            await recover_uploads()
        except asyncio.CancelledError:
            raise
        except Exception as _e:
            print(f"[RECOVERY] Ошибка цикла: {_e!r}", flush=True)
        await asyncio.sleep(RECOVERY_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.files.routers import recover_uploads
    await recover_uploads()

    recovery_task = asyncio.create_task(_recovery_loop())
    try:
        yield
    finally:
        recovery_task.cancel()
        await asyncio.gather(recovery_task, return_exceptions=True)


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
from src.stats.routers import router as stats_router

app.include_router(files_router)
app.include_router(split_router)
app.include_router(stats_router)
