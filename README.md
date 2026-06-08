```bash
docker compose exec scan-app alembic revision --autogenerate
docker compose exec scan-app alembic upgrade head
```

### Connect Admin (dev)
```bash
docker compose -f docker-compose-dev.yml exec scan-app python -m src.scripts.create_admin
```