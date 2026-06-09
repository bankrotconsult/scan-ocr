```bash
docker compose exec scan-app alembic revision --autogenerate
docker compose exec scan-app alembic upgrade head
```

### Connect Admin (dev)
```bash
docker compose exec scan-app python -m src.scripts.create_admin
```

### build command
```commandline
docker compose down -v && docker compose up --build
```