# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI OCR service with PostgreSQL, SQLAdmin panel, async SQLAlchemy, and Poetry. The `src/ocr/` module is a placeholder — OCR logic has not yet been implemented.

## Commands

```bash
# Start the application
docker compose up

# Apply migrations
docker compose exec app alembic revision --autogenerate
docker compose exec app alembic upgrade head

# Create an admin user
docker compose exec app python -m src.scripts.create_admin

# Lint
ruff check .

# Type check
mypy .

# Tests
pytest
```

## Architecture

### Layer pattern (per domain)

Each domain (`files`, `users`) follows the same four-layer stack:

```
Router (routers.py)
  └─ Service (service.py)        ← business logic
       └─ Repository (repository.py)  ← DB queries, returns DTOs
            └─ Model (models.py)      ← SQLAlchemy ORM
```

**DTOs** (`dto.py`) are plain Python `@dataclass` objects used for internal data transfer between layers. **Schemas** (`schemas.py`) are Pydantic models used only at the API boundary (request/response serialization).

The base repository (`src/utils/repository.py`) defines `AbstractRepository` and `SQLAlchemyRepository`. Domain repositories extend `SQLAlchemyRepository` and set `model = <OrmClass>`.

### Database session

`src/db/db.py` exposes `db_session()` — an async context manager that commits on success and rolls back on exception. Sessions are created per request inside routers, not injected via FastAPI dependency injection.

```python
async with db_session() as s:
    result = await SomeService(SomeRepository(s)).do_something()
```

### Admin panel

`src/admin_flask/app.py` mounts SQLAdmin at `/admin` via `init_admin(app)`. Authentication uses a session-based `AdminAuth` backend (username + password against the `users` table, `is_active=True` required). Admin views are registered in `src/files/admin.py` and `src/users/admin.py`.

### Configuration

`src/config/base.py` loads env vars via `python-dotenv`. Required vars: `DATABASE_URL` (asyncpg), `SYNC_DATABASE_URL` (psycopg2, used by Alembic), `SECRET_KEY`. `DEBUG` defaults to `True`; when `False`, an HTTP middleware forces HTTPS scheme.

### Migrations

Alembic config is at `alembic.ini`; scripts live in `src/migrations/`. The `env.py` imports all models explicitly — **new models must be imported there** for autogenerate to detect them.

### Naming inconsistency

`src/files/service.py` defines the class as `RegionService` but it is used as `FileService` in `src/files/routers.py`. This is a known inconsistency.
